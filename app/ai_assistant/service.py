from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_assistant.provider import BedrockConverseProvider
from app.ai_assistant.repository import AssistantRepository
from app.ai_assistant.schemas import (
    AssistantMessageRequest,
    AssistantProgressResponse,
    AssistantSessionCreate,
    ToolExecutionResponse,
)
from app.ai_assistant.tools import ALLOWED_TOOL_NAMES, BEDROCK_TOOL_CONFIG
from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import AppError, PermissionDeniedError, ResourceNotFoundError
from app.storage.service import StorageService
from app.valuation.f03_repository import F03Repository
from app.valuation.f03_schemas import F03DraftUpdate
from app.valuation.f03_service import F03Service
from app.valuation.models import AssistantMessageRecord, AssistantSessionRecord
from app.valuation.operations.calculation_service import CalculationService
from app.valuation.operations.report_service import ReportService
from app.valuation.operations.validation_service import ValidationService
from app.valuation.requirements import FORM_REQUIREMENTS
from app.valuation.schemas import FormCode
from app.valuation.service import ValuationService


def normalize_f03_confirmed_fields(values: dict[str, Any]) -> dict[str, Any]:
    """Map the guide-facing date name to the existing database field name."""
    fields = dict(values)
    valuation_date = fields.pop("valuation_date", None)
    if valuation_date is None:
        return fields

    valuation_base_date = fields.get("valuation_base_date")
    if valuation_base_date is not None and valuation_base_date != valuation_date:
        raise AppError(
            "VALUATION_DATE_CONFLICT",
            "valuation_date 與 valuation_base_date 不可填入不同值",
            422,
        )
    fields["valuation_base_date"] = valuation_date
    return fields


class AssistantService:
    def __init__(
        self,
        session: AsyncSession,
        repository: AssistantRepository | None = None,
        storage: StorageService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or AssistantRepository(session)
        self.valuation = ValuationService(session)
        self.f03 = F03Service(session)
        self.f03_repository = F03Repository(session)
        self.settings = get_settings()
        self.storage = storage

    async def create_session(
        self, payload: AssistantSessionCreate, user: User
    ) -> AssistantSessionRecord:
        await self.valuation._owned_editable_case(payload.case_id, user)
        form = await self.f03._require_f03_form(
            payload.case_id, payload.form_instance_id
        )
        if form.form_status != "DRAFT":
            raise AppError(
                "FORM_STATE_CONFLICT",
                "只能為 F03 草稿建立 AI 工作階段",
                409,
            )
        provider = self.settings.ai_provider.upper()
        model_id = (
            self.settings.bedrock_model_id
            if provider == "BEDROCK"
            else "mock-f03-v1"
        )
        record = AssistantSessionRecord(
            case_id=payload.case_id,
            user_id=user.user_id,
            form_instance_id=payload.form_instance_id,
            selected_form_type="F03",
            provider=provider,
            model_id=model_id,
            prompt_version=self.settings.ai_prompt_version,
        )
        await self.repository.create_session(record)
        await self.refresh_progress(record)
        await self._add_message(
            record,
            role="ASSISTANT",
            content=self._mock_reply(record, 0, False),
            model_id=model_id,
        )
        return await self.repository.save_session(record)

    async def get_session(
        self, session_id: UUID, user: User
    ) -> AssistantSessionRecord:
        record = await self._session_or_404(session_id)
        self._require_session_user(record, user)
        return record

    async def progress(
        self, session_id: UUID, user: User
    ) -> AssistantProgressResponse:
        record = await self.get_session(session_id, user)
        return await self.refresh_progress(record)

    async def refresh_progress(
        self, record: AssistantSessionRecord
    ) -> AssistantProgressResponse:
        requirement = FORM_REQUIREMENTS["F03"]
        draft = await self.f03_repository.get_draft_for_form(
            record.case_id, record.form_instance_id
        )
        missing_fields: list[str] = []
        if draft is None:
            missing_fields.extend(requirement.required_fields)

        document_types = await self.repository.list_active_document_types(record.case_id)
        missing_documents = [
            item for item in requirement.required_documents if item not in document_types
        ]
        confirmed_count, pending_count = await self.repository.candidate_counts(
            record.case_id
        )

        if missing_fields:
            current_step = "COLLECT_FIELDS"
        elif missing_documents:
            current_step = "COLLECT_DOCUMENTS"
        elif pending_count:
            current_step = "REVIEW_EXTRACTION"
        else:
            current_step = "READY_TO_SUBMIT"

        record.current_step = current_step
        record.missing_fields = missing_fields
        record.missing_documents = missing_documents
        await self.repository.save_session(record)
        total_items = len(requirement.required_fields) + len(
            requirement.required_documents
        )
        completed_items = total_items - len(missing_fields) - len(missing_documents)
        return AssistantProgressResponse(
            assistant_session_id=record.assistant_session_id,
            current_step=current_step,
            missing_fields=missing_fields,
            missing_documents=missing_documents,
            confirmed_candidate_count=confirmed_count,
            pending_candidate_count=pending_count,
            completed_items=completed_items,
            total_items=total_items,
        )

    async def send_message(
        self,
        session_id: UUID,
        payload: AssistantMessageRequest,
        user: User,
        request_id: UUID | None,
    ) -> tuple[AssistantSessionRecord, str, AssistantProgressResponse, list[ToolExecutionResponse]]:
        record = await self.get_session(session_id, user)
        if record.session_status != "ACTIVE":
            raise AppError("ASSISTANT_SESSION_CLOSED", "AI 工作階段已關閉", 409)
        await self.valuation._owned_editable_case(record.case_id, user)
        await self._add_message(
            record,
            role="USER",
            content=payload.content,
            request_id=request_id,
        )

        tools: list[ToolExecutionResponse] = []
        if record.provider == "BEDROCK":
            reply = await self._bedrock_reply(
                record, payload, user, tools, request_id
            )
        else:
            for tool_name in (
                "get_case_summary",
                "get_form_requirements",
                "get_missing_items",
                "get_extracted_fields",
            ):
                result = await self._execute_tool(tool_name, record, payload, user)
                tools.append(
                    await self._record_tool(record, tool_name, result, request_id)
                )
            apply_requested = bool(
                payload.confirmed_fields or payload.confirmed_candidate_ids
            )
            if apply_requested:
                if payload.confirm_apply:
                    result = await self._execute_tool(
                        "apply_confirmed_fields", record, payload, user
                    )
                    tools.append(
                        await self._record_tool(
                            record,
                            "apply_confirmed_fields",
                            result,
                            request_id,
                        )
                    )
                else:
                    result = {
                        "status": "PENDING",
                        "confirmation_required": True,
                        "field_names": sorted(payload.confirmed_fields),
                        "candidate_count": len(payload.confirmed_candidate_ids),
                    }
                    tools.append(
                        await self._record_tool(
                            record,
                            "apply_confirmed_fields",
                            result,
                            request_id,
                            status="PENDING",
                        )
                    )
            for tool_name, requested, confirmation_required in (
                ("run_calculation", payload.run_calculation, True),
                ("run_validation", payload.run_validation, False),
                ("generate_report_pdf", payload.generate_report_pdf, True),
            ):
                if not requested:
                    continue
                if confirmation_required and not payload.confirm_action:
                    result = {
                        "status": "PENDING",
                        "confirmation_required": True,
                    }
                    tools.append(
                        await self._record_tool(
                            record,
                            tool_name,
                            result,
                            request_id,
                            status="PENDING",
                        )
                    )
                    continue
                result = await self._execute_tool(
                    tool_name, record, payload, user, request_id
                )
                status = str(result.get("status", "SUCCESS"))
                tools.append(
                    await self._record_tool(
                        record, tool_name, result, request_id, status=status
                    )
                )
            if payload.nearest_facility is not None:
                result = await self._execute_tool(
                    "get_nearest_facility", record, payload, user, request_id
                )
                status = str(result.get("status", "SUCCESS"))
                tools.append(
                    await self._record_tool(
                        record,
                        "get_nearest_facility",
                        result,
                        request_id,
                        status=status,
                    )
                )
            progress = await self.refresh_progress(record)
            reply = self._operation_reply(
                record,
                progress.pending_candidate_count,
                apply_requested and not payload.confirm_apply,
                tools,
            )

        progress = await self.refresh_progress(record)
        await self._add_message(
            record,
            role="ASSISTANT",
            content=reply,
            request_id=request_id,
            model_id=record.model_id,
        )
        return record, reply, progress, tools

    async def _bedrock_reply(
        self,
        record: AssistantSessionRecord,
        payload: AssistantMessageRequest,
        user: User,
        tools: list[ToolExecutionResponse],
        request_id: UUID | None,
    ) -> str:
        provider = BedrockConverseProvider(self.settings, BEDROCK_TOOL_CONFIG)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [{"text": payload.content}]}
        ]
        applied = False
        for _round in range(self.settings.ai_max_tool_rounds):
            response = await provider.converse(messages)
            if not response.tool_calls:
                return response.text or self._mock_reply(record, 0, False)
            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            operation_executed: set[str] = set()
            for call in response.tool_calls:
                if call.name not in ALLOWED_TOOL_NAMES:
                    raise AppError(
                        "AI_TOOL_NOT_ALLOWED",
                        f"AI 不可呼叫工具 {call.name}",
                        422,
                    )
                if call.name in {"apply_confirmed_fields", "save_form_draft"}:
                    if applied:
                        result = {"status": "SUCCESS", "duplicate_ignored": True}
                    elif not payload.confirm_apply:
                        result = {
                            "status": "PENDING",
                            "confirmation_required": True,
                        }
                    else:
                        result = await self._execute_tool(
                            "apply_confirmed_fields", record, payload, user, tool_input=call.input
                        )
                        applied = True
                elif call.name in {
                    "run_calculation",
                    "run_validation",
                    "generate_report_pdf",
                }:
                    requested = {
                        "run_calculation": payload.run_calculation,
                        "run_validation": payload.run_validation,
                        "generate_report_pdf": payload.generate_report_pdf,
                    }[call.name]
                    confirmation_required = call.name in {
                        "run_calculation",
                        "generate_report_pdf",
                    }
                    if not requested:
                        result = {
                            "status": "DENIED",
                            "reason": "使用者未在結構化請求中要求此操作",
                        }
                    elif confirmation_required and not payload.confirm_action:
                        result = {
                            "status": "PENDING",
                            "confirmation_required": True,
                        }
                    elif call.name in operation_executed:
                        result = {"status": "SUCCESS", "duplicate_ignored": True}
                    else:
                        result = await self._execute_tool(
                            call.name, record, payload, user, request_id, call.input
                        )
                        operation_executed.add(call.name)
                elif call.name == "get_nearest_facility":
                    if payload.nearest_facility is None:
                        result = {
                            "status": "DENIED",
                            "reason": "使用者未在結構化請求中確認步行距離查詢",
                        }
                    elif call.name in operation_executed:
                        result = {"status": "SUCCESS", "duplicate_ignored": True}
                    else:
                        result = await self._execute_tool(
                            call.name, record, payload, user, request_id
                        )
                        operation_executed.add(call.name)
                else:
                    result = await self._execute_tool(
                        call.name, record, payload, user, request_id, call.input
                    )
                status = str(result.get("status", "SUCCESS"))
                tools.append(
                    await self._record_tool(
                        record, call.name, result, request_id, status=status
                    )
                )
                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": call.tool_use_id,
                            "content": [{"json": result}],
                            "status": "success" if status == "SUCCESS" else "error",
                        }
                    }
                )
            messages.append({"role": "user", "content": tool_results})
        raise AppError("AI_TOOL_LIMIT", "AI 工具呼叫次數已達上限", 503)

    async def _execute_tool(
        self,
        tool_name: str,
        record: AssistantSessionRecord,
        payload: AssistantMessageRequest,
        user: User,
        request_id: UUID | None = None,
        tool_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tool_input = tool_input or {}
        if tool_name == "get_case_summary":
            case = await self.valuation._case_or_404(record.case_id)
            parcels = await self.valuation.repository.list_parcels(record.case_id)
            return {
                "status": "SUCCESS",
                "case_id": str(case.case_id),
                "case_no": case.case_no,
                "case_status": case.case_status,
                "valuation_base_date": case.valuation_base_date.isoformat(),
                "parcel_count": len(parcels),
            }
        if tool_name == "get_form_requirements":
            requirement = self.valuation.form_requirement(FormCode.F03)
            return {"status": "SUCCESS", **requirement.model_dump(mode="json")}
        if tool_name == "get_missing_items":
            progress = await self.refresh_progress(record)
            return {"status": "SUCCESS", **progress.model_dump(mode="json")}
        if tool_name == "get_extracted_fields":
            candidates = await self.repository.list_candidate_summaries(record.case_id)
            return {"status": "SUCCESS", "candidates": candidates}
        if tool_name in {"apply_confirmed_fields", "save_form_draft"}:
            return await self._apply_confirmed_fields(record, payload, user)
        if tool_name == "run_calculation":
            result = await CalculationService(self.session).run_f03(
                record.case_id,
                record.form_instance_id,
                user,
                request_id,
            )
            return {"status": "SUCCESS", **result.model_dump(mode="json")}
        if tool_name == "run_validation":
            if self.storage is None:
                raise AppError("STORAGE_REQUIRED", "檢核需要 MinIO 連線", 503)
            result = await ValidationService(self.session, self.storage).run_f03(
                record.case_id,
                record.form_instance_id,
                user,
                request_id,
            )
            return {"status": "SUCCESS", **result.model_dump(mode="json")}
        if tool_name == "generate_report_pdf":
            if self.storage is None:
                raise AppError("STORAGE_REQUIRED", "產生 PDF 需要 MinIO 連線", 503)
            result = await ReportService(self.session, self.storage).generate_f03(
                record.case_id,
                record.form_instance_id,
                user,
                request_id,
            )
            return {"status": "SUCCESS", **result.model_dump(mode="json")}
        if tool_name == "get_nearest_facility":
            if payload.nearest_facility is None or not payload.confirm_action:
                return {
                    "status": "DENIED",
                    "reason": "步行距離查詢尚未由使用者結構化確認",
                }
            from app.valuation.facilities.schemas import FacilityOriginType
            from app.valuation.facilities.service import FacilityService
            from app.valuation.report_packages.repository import ReportPackageRepository

            request = payload.nearest_facility
            resolved_lat = request.origin_lat
            resolved_lng = request.origin_lng
            if request.origin_type == FacilityOriginType.BENCHMARK_LAND_ENTRANCE:
                benchmark = await ReportPackageRepository(
                    self.session
                ).get_benchmark_land(record.case_id, request.origin_reference_id)
                if benchmark is None:
                    raise AppError(
                        "CROSS_CASE_REFERENCE",
                        "比準地起點不存在、已停用或不屬於此案件",
                        422,
                    )
                resolved_lat = resolved_lat or benchmark.latitude
                resolved_lng = resolved_lng or benchmark.longitude
            elif request.origin_type == FacilityOriginType.SUBJECT_PARCEL_ENTRANCE:
                parcel = await self.valuation.repository.get_parcel(
                    record.case_id, request.origin_reference_id
                )
                if parcel is None:
                    raise AppError(
                        "CROSS_CASE_REFERENCE",
                        "宗地起點不存在或不屬於此案件",
                        422,
                    )

            facility_service = FacilityService()
            try:
                result = await facility_service.find_nearest_facility(
                    request,
                    resolved_lat=resolved_lat,
                    resolved_lng=resolved_lng,
                )
            finally:
                await facility_service.close()
            if not result:
                return {"status": "FAILED", "reason": "找不到距離內設施或無法解析地址"}
            from app.valuation.facilities.schemas import NearestFacilityResponse

            serialized = NearestFacilityResponse.model_validate(result).model_dump(
                mode="json"
            )
            return {"status": "SUCCESS", **serialized}
        raise AppError("AI_TOOL_NOT_ALLOWED", f"不允許的工具：{tool_name}", 422)

    async def _apply_confirmed_fields(
        self,
        record: AssistantSessionRecord,
        payload: AssistantMessageRequest,
        user: User,
    ) -> dict[str, Any]:
        fields = normalize_f03_confirmed_fields(payload.confirmed_fields)
        benchmark_land_no = fields.pop("benchmark_land_no", None)
        if benchmark_land_no is not None:
            benchmark_id = await self.repository.resolve_benchmark_land_no(
                record.case_id, str(benchmark_land_no)
            )
            if benchmark_id is None:
                raise AppError(
                    "BENCHMARK_LAND_NOT_FOUND",
                    "找不到同案件且地號完全相符的啟用比準地",
                    422,
                )
            fields["benchmark_land_id"] = benchmark_id

        candidate_records = []
        for candidate_id in payload.confirmed_candidate_ids:
            candidate = await self.repository.get_confirmed_candidate(
                record.case_id, candidate_id
            )
            if candidate is None:
                raise AppError(
                    "CANDIDATE_NOT_CONFIRMED",
                    "候選欄位不存在、已套用或尚未確認",
                    422,
                )
            value = candidate.confirmed_value
            if candidate.field_name == "benchmark_land_no":
                benchmark_id = await self.repository.resolve_benchmark_land_no(
                    record.case_id, str(value)
                )
                if benchmark_id is None:
                    raise AppError(
                        "BENCHMARK_LAND_NOT_FOUND",
                        "候選比準地地號無法對應同案件比準地",
                        422,
                    )
                fields.setdefault("benchmark_land_id", benchmark_id)
            elif candidate.field_name == "valuation_base_date":
                fields.setdefault("valuation_base_date", value)
            else:
                raise AppError(
                    "FIELD_NOT_ALLOWED",
                    f"候選欄位 {candidate.field_name} 不可寫入 F03 草稿",
                    422,
                )
            candidate_records.append(candidate)

        if not fields:
            raise AppError("NO_CONFIRMED_FIELDS", "沒有可套用的已確認欄位", 422)
        try:
            draft_payload = F03DraftUpdate.model_validate(fields)
        except Exception as exc:
            raise AppError(
                "CONFIRMED_FIELD_INVALID",
                "已確認欄位不符合 F03 Schema，請修正後再套用",
                422,
            ) from exc
        draft = await self.f03.update_draft(
            record.case_id,
            record.form_instance_id,
            draft_payload,
            user,
        )
        for candidate in candidate_records:
            await self.repository.mark_candidate_applied(
                candidate, record.form_instance_id
            )
        return {
            "status": "SUCCESS",
            "benchmark_valuation_id": str(draft.benchmark_valuation_id),
            "applied_fields": sorted(fields),
            "applied_candidate_count": len(candidate_records),
        }

    async def _record_tool(
        self,
        record: AssistantSessionRecord,
        tool_name: str,
        result: dict[str, Any],
        request_id: UUID | None,
        status: str = "SUCCESS",
    ) -> ToolExecutionResponse:
        record.last_tool_name = tool_name
        record.last_tool_status = status
        summary = {
            "status": status,
            "result_keys": sorted(result),
            "candidate_count": len(result.get("candidates", [])),
        }
        tool_input_summary: dict[str, Any] = {}
        if tool_name in {"apply_confirmed_fields", "save_form_draft"}:
            tool_input_summary = {
                "field_names": sorted(
                    result.get("applied_fields", result.get("field_names", []))
                ),
                "candidate_count": result.get(
                    "applied_candidate_count", result.get("candidate_count", 0)
                ),
            }
        await self._add_message(
            record,
            role="TOOL",
            content=f"{tool_name}: {status}",
            tool_name=tool_name,
            tool_input_summary=tool_input_summary,
            tool_result_summary=summary,
            request_id=request_id,
        )
        return ToolExecutionResponse(tool_name=tool_name, status=status, result=result)

    async def _add_message(
        self,
        record: AssistantSessionRecord,
        *,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_input_summary: dict[str, Any] | None = None,
        tool_result_summary: dict[str, Any] | None = None,
        request_id: UUID | None = None,
        model_id: str | None = None,
    ) -> None:
        await self.repository.add_message(
            AssistantMessageRecord(
                assistant_session_id=record.assistant_session_id,
                message_no=await self.repository.next_message_no(
                    record.assistant_session_id
                ),
                role=role,
                content=content,
                tool_name=tool_name,
                tool_input_summary=tool_input_summary or {},
                tool_result_summary=tool_result_summary or {},
                request_id=request_id,
                model_id=model_id,
            )
        )

    async def _session_or_404(self, session_id: UUID) -> AssistantSessionRecord:
        record = await self.repository.get_session(session_id)
        if record is None:
            raise ResourceNotFoundError("AI 工作階段")
        return record

    @staticmethod
    def _require_session_user(record: AssistantSessionRecord, user: User) -> None:
        if record.user_id != user.user_id:
            raise PermissionDeniedError("只能存取自己的 AI 工作階段")

    @staticmethod
    def _mock_reply(
        record: AssistantSessionRecord,
        pending_candidates: int,
        confirmation_pending: bool,
    ) -> str:
        if confirmation_pending:
            return "已收到待套用欄位，但尚未寫入。確認內容後請將 confirm_apply 設為 true。"
        parts = ["目前 F03 製作進度已由後端重新檢查。"]
        if record.missing_fields:
            parts.append("缺少欄位：" + "、".join(record.missing_fields) + "。")
        if record.missing_documents:
            parts.append("缺少文件：" + "、".join(record.missing_documents) + "。")
        if pending_candidates:
            parts.append(f"另有 {pending_candidates} 個擷取候選欄位等待使用者確認。")
        if not record.missing_fields and not record.missing_documents and not pending_candidates:
            parts.append("必要欄位與文件已齊備，可進行後續計算與製作前檢核。")
        else:
            parts.append("請先補齊或確認上述項目；系統不會自行填入未確認資料。")
        return "".join(parts)

    @staticmethod
    def _operation_reply(
        record: AssistantSessionRecord,
        pending_candidates: int,
        confirmation_pending: bool,
        tools: list[ToolExecutionResponse],
    ) -> str:
        parts = [
            AssistantService._mock_reply(
                record, pending_candidates, confirmation_pending
            )
        ]
        for tool in tools:
            if tool.tool_name == "run_calculation":
                if tool.status == "PENDING":
                    parts.append("計算尚未執行；確認後請將 confirm_action 設為 true。")
                elif tool.status == "SUCCESS" and "result" in tool.result:
                    parts.append(f"F03 計算完成，結果為 {tool.result['result']} TWD。")
            elif tool.tool_name == "run_validation" and tool.status == "SUCCESS":
                failed = tool.result.get("failed_count", 0)
                parts.append(f"製作前檢核完成，ERROR 共 {failed} 項。")
                hints = tool.result.get("correction_hints", [])
                if hints:
                    parts.append("請修正：" + "；".join(hints))
            elif tool.tool_name == "generate_report_pdf":
                if tool.status == "PENDING":
                    parts.append("PDF 尚未產生；確認後請將 confirm_action 設為 true。")
                elif tool.status == "SUCCESS":
                    parts.append("F03 PDF 已產生：" + str(tool.result.get("download_path")))
        return "".join(parts)

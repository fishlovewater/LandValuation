import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_assistant.chat_service import (
    answer_general_chat,
    answer_hybrid_chat,
    answer_structured_case_chat,
)
from app.ai_assistant.provider import BedrockConverseProvider, OllamaChatProvider
from app.ai_assistant.repository import AssistantRepository
from app.ai_assistant.routing import AssistantAnswerRoute, analyze_assistant_question
from app.ai_assistant.schemas import (
    AssistantClaim,
    AssistantCitation,
    AssistantMessageRequest,
    AssistantProgressResponse,
    AssistantQuestionRequest,
    AssistantQuestionResponse,
    AssistantSessionCreate,
    ToolExecutionResponse,
)
from app.ai_assistant.tools import (
    ALLOWED_TOOL_NAMES,
    BEDROCK_TOOL_CONFIG,
    OLLAMA_TOOL_CONFIG,
)
from app.auth.models import User
from app.auth.service import permission_codes
from app.core.config import get_settings
from app.core.exceptions import AppError, PermissionDeniedError, ResourceNotFoundError
from app.knowledge.answer_service import answer_knowledge_question
from app.knowledge.schemas import (
    KnowledgeAnswerResponse,
    KnowledgeAnswerStatus,
    KnowledgeSearchRequest,
)
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


ASSISTANT_TOOL_PERMISSIONS = {
    "get_case_summary": frozenset({"valuation.read"}),
    "get_form_requirements": frozenset({"valuation.read"}),
    "get_missing_items": frozenset({"valuation.read"}),
    "get_extracted_fields": frozenset({"valuation.read"}),
    "get_nearest_facility": frozenset({"valuation.read"}),
    "apply_confirmed_fields": frozenset({"valuation.read", "valuation.update"}),
    "save_form_draft": frozenset({"valuation.read", "valuation.update"}),
    "run_calculation": frozenset({"valuation.read", "valuation.update"}),
    "run_validation": frozenset({"valuation.read", "valuation.update"}),
    "generate_report_pdf": frozenset({"valuation.read", "valuation.update"}),
}


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
            "估價基準日出現兩個不同值，請確認後再送出。",
            422,
        )
    fields["valuation_base_date"] = valuation_date
    return fields


class AssistantService:
    _UNSUPPORTED_QUESTION_COPY = "目前沒有足夠的可讀適用來源，無法支持這項回答。"

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
        # An Assistant session is also useful after an appraisal has been
        # submitted (for example, to inspect the case, extraction results, or
        # cited knowledge).  Session creation therefore follows the normal
        # read authorization boundary rather than the editable-case boundary.
        # Mutating tools keep their own stricter state/ownership checks in the
        # valuation services that actually perform the write.
        await self.valuation.get_case(payload.case_id, user)
        await self.f03._require_f03_form(
            payload.case_id, payload.form_instance_id
        )
        provider = self.settings.ai_provider.upper()
        if provider == "BEDROCK":
            model_id = self.settings.bedrock_model_id
        elif provider == "OLLAMA":
            model_id = self.settings.ollama_model
        else:
            model_id = "mock-f03-v1"
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

    async def ask_question(
        self,
        session_id: UUID,
        payload: AssistantQuestionRequest,
        user: User,
        storage: StorageService,
    ) -> AssistantQuestionResponse:
        record = await self.get_session(session_id, user)
        existing = await self.repository.list_messages(
            record.assistant_session_id, limit=20
        )
        history = [
            {
                "role": "user" if item.role == "USER" else "assistant",
                "content": item.content,
            }
            for item in existing
            if item.role in {"USER", "ASSISTANT"}
        ]
        previous_route = self._previous_answer_route(existing)
        await self._add_message(
            record,
            role="USER",
            content=payload.question,
        )
        route = await analyze_assistant_question(
            payload.question,
            has_case_context=True,
            workspace="valuation",
            previous_route=previous_route,
            conversation_history=history,
        )

        if route == AssistantAnswerRoute.CHAT:
            answer, model_id = await answer_general_chat(
                payload.question,
                conversation_history=history,
            )
            response = AssistantQuestionResponse(
                assistant_session_id=record.assistant_session_id,
                answer_status=KnowledgeAnswerStatus.SUPPORTED,
                answer=answer,
                answer_route=route,
                generation_mode="CHAT",
                next_action="CONTINUE_CONVERSATION",
            )
            response_model_id = model_id or record.model_id
        elif route == AssistantAnswerRoute.CASE:
            case_summary = await self._answer_case_question(
                record, payload.question, user
            )
            answer, model_id = await answer_structured_case_chat(
                payload.question,
                case_context={
                    "valuation_session": {
                        "case_id": str(record.case_id),
                        "form_instance_id": (
                            str(record.form_instance_id)
                            if record.form_instance_id
                            else None
                        ),
                        "workflow_summary": case_summary,
                    }
                },
                conversation_history=history,
                fallback_answer=case_summary,
            )
            response = AssistantQuestionResponse(
                assistant_session_id=record.assistant_session_id,
                answer_status=KnowledgeAnswerStatus.SUPPORTED,
                answer=answer,
                answer_route=route,
                generation_mode="STRUCTURED_CASE_DATA",
                next_action="REVIEW_CASE",
            )
            response_model_id = model_id or record.model_id
        else:
            if "knowledge.read" not in permission_codes(user):
                raise PermissionDeniedError("沒有查看法規知識的權限")
            request = KnowledgeSearchRequest(
                question=payload.question,
                case_id=None,
                as_of_date=payload.as_of_date,
                document_types=payload.document_types,
                limit=payload.limit,
            )
            result = (
                await answer_knowledge_question(
                    session=self.session,
                    storage=storage,
                    user=user,
                    request=request,
                    conversation_history=history,
                )
            ).model_copy(update={"answer_route": route.value})
            if route == AssistantAnswerRoute.HYBRID:
                case_summary = await self._answer_case_question(
                    record, payload.question, user
                )
                hybrid_answer, hybrid_model_id = await answer_hybrid_chat(
                    payload.question,
                    case_context={
                        "valuation_session": {
                            "case_id": str(record.case_id),
                            "form_instance_id": (
                                str(record.form_instance_id)
                                if record.form_instance_id
                                else None
                            ),
                            "workflow_summary": case_summary,
                        }
                    },
                    case_summary=case_summary,
                    knowledge_result=result.model_dump(mode="json"),
                    conversation_history=history,
                )
                result = result.model_copy(
                    update={
                        "answer": hybrid_answer,
                        "generation_mode": "HYBRID_SYNTHESIS",
                        "model_id": hybrid_model_id or result.model_id,
                    }
                )
            response = self._question_response(record, result)
            response_model_id = result.model_id or record.model_id
        await self._add_message(
            record,
            role="ASSISTANT",
            content=response.answer,
            model_id=response_model_id,
            response_payload=response.model_dump(mode="json"),
        )
        return response

    @staticmethod
    def _previous_answer_route(
        records: list[AssistantMessageRecord],
    ) -> AssistantAnswerRoute | None:
        for item in reversed(records):
            if item.role != "ASSISTANT" or not isinstance(item.response_payload, dict):
                continue
            raw = item.response_payload.get("answer_route")
            try:
                return AssistantAnswerRoute(raw)
            except (TypeError, ValueError):
                continue
        return None

    async def _answer_case_question(
        self,
        record: AssistantSessionRecord,
        question: str,
        user: User,
    ) -> str:
        """Answer common case questions from permission-checked structured data."""

        self._require_tool_permissions(user, "get_case_summary")
        summary = await self._execute_tool(
            "get_case_summary",
            record,
            AssistantMessageRequest(content=question),
            user,
        )
        progress = await self.refresh_progress(record)
        normalized = question.lower()

        if any(term in normalized for term in ("缺件", "缺少", "待補", "還缺")):
            missing: list[str] = []
            if progress.missing_fields:
                missing.append("缺少欄位：" + "、".join(progress.missing_fields))
            if progress.missing_documents:
                missing.append("缺少文件：" + "、".join(progress.missing_documents))
            if not missing:
                return "目前系統沒有記錄尚未補齊的必要欄位或文件。"
            return "；".join(missing) + "。"

        if any(term in normalized for term in ("ocr", "辨識", "擷取欄位", "欄位辨識")):
            self._require_tool_permissions(user, "get_extracted_fields")
            candidates = await self.repository.list_candidate_summaries(record.case_id)
            pending = [
                item
                for item in candidates
                if item.get("status") in {"EXTRACTED", "NEEDS_CONFIRMATION"}
            ]
            confirmed = [
                item
                for item in candidates
                if item.get("status") in {"CONFIRMED", "APPLIED"}
            ]
            return (
                f"目前共有 {len(candidates)} 筆辨識欄位，其中已確認 {len(confirmed)} 筆，"
                f"待確認 {len(pending)} 筆。"
            )

        if any(term in normalized for term in ("必填", "需要哪些資料", "需要哪些文件")):
            requirement = FORM_REQUIREMENTS["F03"]
            return (
                "目前 F03 的必要欄位為："
                + "、".join(requirement.required_fields)
                + "；必要文件為："
                + "、".join(requirement.required_documents)
                + "。"
            )

        case_no = str(summary.get("case_no") or "目前案件")
        status = str(summary.get("case_status") or "狀態待確認")
        valuation_date = str(summary.get("valuation_base_date") or "未設定")
        parcel_count = int(summary.get("parcel_count") or 0)
        return (
            f"案件 {case_no} 目前狀態為 {status}，估價基準日為 {valuation_date}，"
            f"系統記錄 {parcel_count} 筆宗地資料。"
        )

    @classmethod
    def _question_response(
        cls,
        record: AssistantSessionRecord,
        result: KnowledgeAnswerResponse,
    ) -> AssistantQuestionResponse:
        if result.answer_status != KnowledgeAnswerStatus.SUPPORTED:
            return AssistantQuestionResponse(
                assistant_session_id=record.assistant_session_id,
                answer_status=result.answer_status,
                answer=cls._UNSUPPORTED_QUESTION_COPY,
                answer_route=AssistantAnswerRoute(result.answer_route),
                generation_mode=result.generation_mode,
                next_action=result.next_action,
                clarification_question=result.clarification_question,
                unreadable_sources=result.unreadable_sources,
            )

        citations = [
            AssistantCitation(
                citation_id=citation.chunk_id,
                document_id=citation.document_id,
                document_title=citation.document_title,
                document_code=citation.document_code,
                version_no=citation.version_no,
                effective_from=citation.effective_from,
                effective_to=citation.effective_to,
                page_start=citation.page_start,
                page_end=citation.page_end,
                section_title=citation.section_title,
                article_no=citation.article_no,
                quoted_text=citation.quoted_text,
                supporting_quote=citation.supporting_quote,
                supported_claim=citation.supported_claim,
            )
            for citation in result.citations
        ]
        citation_ids = [citation.citation_id for citation in citations]
        citation_ids_by_claim: dict[str, list[UUID]] = {}
        for citation in citations:
            claim_text = (citation.supported_claim or "").strip()
            if not claim_text:
                continue
            claim_citation_ids = citation_ids_by_claim.setdefault(claim_text, [])
            if citation.citation_id not in claim_citation_ids:
                claim_citation_ids.append(citation.citation_id)
        claims = [
            AssistantClaim(text=claim_text, citation_ids=claim_citation_ids)
            for claim_text, claim_citation_ids in citation_ids_by_claim.items()
        ]
        citation_id_set = set(citation_ids)
        claim_citation_ids = [
            citation_id
            for claim in claims
            for citation_id in claim.citation_ids
        ]
        graph_is_complete = (
            bool(claims)
            and len(citation_ids) == len(citation_id_set)
            and all(
                citation.supported_claim and citation.supported_claim.strip()
                for citation in citations
            )
            and len(claim_citation_ids) == len(citation_ids)
            and len(claim_citation_ids) == len(set(claim_citation_ids))
            and set(claim_citation_ids) == citation_id_set
        )
        if not graph_is_complete or any(
            citation_id not in set(citation_ids)
            for claim in claims
            for citation_id in claim.citation_ids
        ):
            return AssistantQuestionResponse(
                assistant_session_id=record.assistant_session_id,
                answer_status=KnowledgeAnswerStatus.EVIDENCE_ONLY,
                answer=cls._UNSUPPORTED_QUESTION_COPY,
                answer_route=AssistantAnswerRoute(result.answer_route),
                generation_mode=result.generation_mode,
                next_action=result.next_action,
                clarification_question=result.clarification_question,
                unreadable_sources=result.unreadable_sources,
            )
        return AssistantQuestionResponse(
            assistant_session_id=record.assistant_session_id,
            answer_status=result.answer_status,
            answer=result.answer,
            answer_route=AssistantAnswerRoute(result.answer_route),
            generation_mode=result.generation_mode,
            next_action=result.next_action,
            clarification_question=result.clarification_question,
            claims=claims,
            citations=citations,
            unreadable_sources=result.unreadable_sources,
        )

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
            raise AppError("ASSISTANT_SESSION_CLOSED", "目前的智能助理對話已結束，請重新開啟智能助理。", 409)
        # Read-only conversation/tool calls remain available for submitted or
        # reviewed cases.  Any tool that mutates valuation data is checked by
        # its underlying service (F03 update/calculation/validation/report),
        # which still enforces editable case/form state.
        await self.valuation.get_case(record.case_id, user)
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
        elif record.provider == "OLLAMA":
            reply = await self._ollama_reply(
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

    async def _ollama_reply(
        self,
        record: AssistantSessionRecord,
        payload: AssistantMessageRequest,
        user: User,
        tools: list[ToolExecutionResponse],
        request_id: UUID | None,
    ) -> str:
        provider = OllamaChatProvider(self.settings, OLLAMA_TOOL_CONFIG)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": payload.content}
        ]
        applied = False
        for _round in range(self.settings.ai_max_tool_rounds):
            response = await provider.converse(messages)
            if not response.tool_calls:
                return response.text or self._mock_reply(record, 0, False)
            messages.append(response.content)
            operation_executed: set[str] = set()
            for call in response.tool_calls:
                if call.name not in ALLOWED_TOOL_NAMES:
                    raise AppError(
                        "AI_TOOL_NOT_ALLOWED",
                        "智能助理提出了目前不支援的操作。",
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
                            "apply_confirmed_fields",
                            record,
                            payload,
                            user,
                            tool_input=call.input,
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
                            call.name,
                            record,
                            payload,
                            user,
                            request_id,
                            call.input,
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
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": call.name,
                        "content": json.dumps(
                            result,
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )
        raise AppError("AI_TOOL_LIMIT", "這次操作步驟過多，請拆成較小的問題再試。", 503)

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
                        "智能助理提出了目前不支援的操作。",
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
        raise AppError("AI_TOOL_LIMIT", "這次操作步驟過多，請拆成較小的問題再試。", 503)

    async def _execute_tool(
        self,
        tool_name: str,
        record: AssistantSessionRecord,
        payload: AssistantMessageRequest,
        user: User,
        request_id: UUID | None = None,
        tool_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_tool_permissions(user, tool_name)
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
                raise AppError("STORAGE_REQUIRED", "目前暫時無法讀取必要文件，請稍後再試。", 503)
            result = await ValidationService(self.session, self.storage).run_f03(
                record.case_id,
                record.form_instance_id,
                user,
                request_id,
            )
            return {"status": "SUCCESS", **result.model_dump(mode="json")}
        if tool_name == "generate_report_pdf":
            if self.storage is None:
                raise AppError("STORAGE_REQUIRED", "目前暫時無法產生 PDF，請稍後再試。", 503)
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
                    "reason": "請先確認步行距離查詢條件",
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
        raise AppError("AI_TOOL_NOT_ALLOWED", "這項操作目前不支援。", 422)

    @staticmethod
    def _require_tool_permissions(user: User, tool_name: str) -> None:
        required = ASSISTANT_TOOL_PERMISSIONS.get(tool_name)
        if required is None:
            raise AppError("AI_TOOL_NOT_ALLOWED", "這項操作目前不支援。", 422)
        if not required.issubset(permission_codes(user)):
            raise PermissionDeniedError()

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
                    "辨識結果不存在、已套用或尚未確認。",
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
                        "辨識到的比準地無法對應本案既有比準地。",
                        422,
                    )
                fields.setdefault("benchmark_land_id", benchmark_id)
            elif candidate.field_name == "valuation_base_date":
                fields.setdefault("valuation_base_date", value)
            else:
                raise AppError(
                    "FIELD_NOT_ALLOWED",
                    "這筆辨識結果不能套用到 F03 草稿。",
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
                "已確認內容的格式不符合 F03 欄位要求，請修正後再套用。",
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
        response_payload: dict[str, Any] | None = None,
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
                response_payload=response_payload or {},
            )
        )

    async def _session_or_404(self, session_id: UUID) -> AssistantSessionRecord:
        record = await self.repository.get_session(session_id)
        if record is None:
            raise ResourceNotFoundError("智能助理對話")
        return record

    @staticmethod
    def _require_session_user(record: AssistantSessionRecord, user: User) -> None:
        if record.user_id != user.user_id:
            raise PermissionDeniedError("只能查看自己的智能助理對話。")

    @staticmethod
    def _mock_reply(
        record: AssistantSessionRecord,
        pending_candidates: int,
        confirmation_pending: bool,
    ) -> str:
        if confirmation_pending:
            return "已收到待套用欄位，但尚未保存。請確認內容後再執行套用。"
        parts = ["目前 F03 製作進度已重新檢查。"]
        if record.missing_fields:
            parts.append("缺少欄位：" + "、".join(record.missing_fields) + "。")
        if record.missing_documents:
            parts.append("缺少文件：" + "、".join(record.missing_documents) + "。")
        if pending_candidates:
            parts.append(f"另有 {pending_candidates} 筆辨識結果等待確認。")
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

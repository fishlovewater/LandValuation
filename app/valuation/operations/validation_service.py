from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import AppError, ResourceNotFoundError
from app.storage.service import StorageService
from app.valuation.models import (
    CaseEventRecord,
    ValidationFindingRecord,
    ValidationRuleRecord,
    ValidationRunRecord,
)
from app.valuation.operations.calculation import FORMULA_VERSION, calculate_f03_price
from app.valuation.operations.repository import OperationsRepository
from app.valuation.operations.schemas import (
    ValidationFindingResponse,
    ValidationResponse,
)
from app.valuation.requirements import FORM_REQUIREMENTS
from app.valuation.service import ValuationService


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class ValidationService:
    def __init__(
        self,
        session: AsyncSession,
        storage: StorageService,
        repository: OperationsRepository | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.repository = repository or OperationsRepository(session)
        self.valuation = ValuationService(session)

    async def run_f03(
        self,
        case_id: UUID,
        form_instance_id: UUID,
        user: User,
        request_id: UUID | None,
    ) -> ValidationResponse:
        case = await self.valuation._owned_editable_case(case_id, user)
        form = await self.repository.get_form(case_id, form_instance_id)
        if form is None:
            raise ResourceNotFoundError("估價表")
        if form.form_code != "F03":
            raise AppError("FORM_TYPE_MISMATCH", "此檢核端點只接受 F03 表單", 422)
        if form.form_status not in {"DRAFT", "READY"}:
            raise AppError("FORM_STATE_CONFLICT", "此 F03 狀態不可執行製作前檢核", 409)

        if request_id is not None:
            existing = await self.repository.validation_for_request(
                case_id, form_instance_id, request_id
            )
            if existing is not None:
                return await self.response(existing)

        version = await self.repository.get_rule_version()
        if version is None:
            raise AppError("VALIDATION_RULES_MISSING", "找不到 F03 MVP 檢核規則", 503)
        rules = await self.repository.list_validation_rules(version.rule_version_id)
        rule_by_code = {rule.rule_code: rule for rule in rules}
        expected_codes = {
            "F03_REQUIRED_FIELDS",
            "F03_REQUIRED_DOCUMENTS",
            "F03_WEIGHT_SUM",
            "F03_METHOD_INPUTS",
            "F03_PRICE_RANGE",
            "F03_CASE_CONSISTENCY",
            "F03_CALCULATION_MATCH",
            "F03_MINIO_OBJECTS",
        }
        if set(rule_by_code) != expected_codes:
            raise AppError("VALIDATION_RULES_INCOMPLETE", "F03 MVP 檢核規則不完整", 503)

        draft = await self.repository.get_f03_draft(case_id, form_instance_id)
        documents = await self.repository.active_documents(case_id)
        document_by_type = {document.document_type: document for document in documents}
        latest_calculation = await self.repository.latest_calculation(
            case_id, form_instance_id
        )
        failures: list[tuple[str, str | None, Any, Any, str]] = []

        def fail(
            code: str,
            field: str | None,
            actual: Any,
            expected: Any,
            message: str,
        ) -> None:
            failures.append((code, field, actual, expected, message))

        if draft is None or draft.benchmark_land_id is None or draft.valuation_base_date is None:
            fail(
                "F03_REQUIRED_FIELDS",
                None,
                None,
                ["benchmark_land_id", "valuation_base_date"],
                "F03 缺少 benchmark_land_id 或 valuation_base_date",
            )

        required_documents = FORM_REQUIREMENTS["F03"].required_documents
        missing_documents = [item for item in required_documents if item not in document_by_type]
        if missing_documents:
            fail(
                "F03_REQUIRED_DOCUMENTS",
                "documents",
                sorted(document_by_type),
                list(required_documents),
                "F03 缺少必要文件：" + "、".join(missing_documents),
            )

        calculation_output = None
        if draft is not None:
            weights = (draft.comparison_weight, draft.income_weight)
            if any(weight < 0 or weight > 1 for weight in weights) or abs(
                sum(weights, Decimal("0")) - Decimal("1")
            ) > Decimal("0.000001"):
                fail(
                    "F03_WEIGHT_SUM",
                    "comparison_weight,income_weight",
                    [format(value, "f") for value in weights],
                    "each 0..1 and sum 1",
                    "比較法與收益法權重必須介於 0 到 1 且合計為 1",
                )
            missing_methods = []
            if draft.comparison_weight > 0 and draft.comparison_price is None:
                missing_methods.append("comparison_price")
            if draft.income_weight > 0 and draft.income_price is None:
                missing_methods.append("income_price")
            if missing_methods:
                fail(
                    "F03_METHOD_INPUTS",
                    ",".join(missing_methods),
                    None,
                    "price required when weight > 0",
                    "權重大於 0 的估價方法缺少價格：" + "、".join(missing_methods),
                )
            prices = [draft.comparison_price, draft.income_price, draft.benchmark_land_price]
            if any(price is not None and price < 0 for price in prices):
                fail(
                    "F03_PRICE_RANGE",
                    "prices",
                    [_json_value(value) for value in prices],
                    ">= 0",
                    "F03 價格不可小於 0",
                )
            benchmark_land = await self.repository.get_benchmark_land(
                case_id, draft.benchmark_land_id
            )
            inconsistent = (
                draft.case_id != case_id
                or draft.form_instance_id != form_instance_id
                or draft.valuation_base_date != case.valuation_base_date
                or benchmark_land is None
            )
            if inconsistent:
                fail(
                    "F03_CASE_CONSISTENCY",
                    "case/form/benchmark/date",
                    {
                        "case_id": str(draft.case_id),
                        "form_instance_id": str(draft.form_instance_id),
                        "valuation_base_date": draft.valuation_base_date.isoformat(),
                        "benchmark_land_found": benchmark_land is not None,
                    },
                    {
                        "case_id": str(case_id),
                        "form_instance_id": str(form_instance_id),
                        "valuation_base_date": case.valuation_base_date.isoformat(),
                    },
                    "案件、表單、比準地或估價日期不一致",
                )
            try:
                calculation_output = calculate_f03_price(
                    comparison_price=draft.comparison_price,
                    comparison_weight=draft.comparison_weight,
                    income_price=draft.income_price,
                    income_weight=draft.income_weight,
                )
            except AppError:
                calculation_output = None

        calculation_matches = False
        if latest_calculation is not None and calculation_output is not None:
            snapshot = latest_calculation.calculation_snapshot
            calculation_matches = (
                snapshot.get("formula_version") == FORMULA_VERSION
                and snapshot.get("input_fingerprint") == calculation_output.input_fingerprint
                and latest_calculation.unit_price == calculation_output.result
                and draft.benchmark_land_price == calculation_output.result
            )
        if not calculation_matches:
            fail(
                "F03_CALCULATION_MATCH",
                "benchmark_land_price",
                None if latest_calculation is None else str(latest_calculation.valuation_id),
                "與目前 F03 資料一致的最新計算結果",
                "最新計算結果與目前 F03 輸入不一致，請重新計算",
            )

        missing_objects: list[str] = []
        for document_type in required_documents:
            document = document_by_type.get(document_type)
            if document is not None and not await self.storage.object_exists(document.object_key):
                missing_objects.append(document_type)
        if missing_objects:
            fail(
                "F03_MINIO_OBJECTS",
                "object_key",
                missing_objects,
                "必要文件皆可正常讀取",
                "必要文件目前無法讀取：" + "、".join(missing_objects),
            )

        # F03 calculation inputs are optional in this system. They may be
        # completed and reviewed by the second review system instead, so they
        # never block Excel-template output here.
        optional_f03_codes = {
            "F03_REQUIRED_FIELDS",
            "F03_WEIGHT_SUM",
            "F03_METHOD_INPUTS",
            "F03_PRICE_RANGE",
            "F03_CASE_CONSISTENCY",
            "F03_CALCULATION_MATCH",
        }
        failures = [
            failure for failure in failures
            if failure[0] not in optional_f03_codes
        ]
        ruleset_snapshot = {
            "rule_set_code": version.rule_set_code,
            "version_no": version.version_no,
            "rules": {
                str(rule.validation_rule_id): {
                    "rule_code": rule.rule_code,
                    "severity": rule.severity,
                    "message": rule.message_template,
                }
                for rule in rules
            },
            "calculation_id": (
                None if latest_calculation is None else str(latest_calculation.valuation_id)
            ),
            "input_fingerprint": (
                None if calculation_output is None else calculation_output.input_fingerprint
            ),
        }
        run = await self.repository.create_validation_run(
            ValidationRunRecord(
                case_id=case_id,
                form_instance_id=form_instance_id,
                run_status="RUNNING",
                triggered_by_user_id=user.user_id,
                rule_version_id=version.rule_version_id,
                ruleset_snapshot=ruleset_snapshot,
                request_id=request_id,
            )
        )
        finding_records = [
            ValidationFindingRecord(
                validation_run_id=run.validation_run_id,
                validation_rule_id=rule_by_code[code].validation_rule_id,
                entity_type="F03",
                entity_id=form_instance_id,
                field_code=field,
                severity=rule_by_code[code].severity,
                actual_value=_json_value(actual),
                expected_value=_json_value(expected),
                finding_message=message,
                request_id=request_id,
            )
            for code, field, actual, expected, message in failures
        ]
        if finding_records:
            await self.repository.add_validation_findings(finding_records)
        run.run_status = "COMPLETED"
        run.warning_count = sum(
            record.severity in {"LOW", "MEDIUM"} for record in finding_records
        )
        run.failed_count = len(finding_records) - run.warning_count
        run.passed_count = len(rules) - len(finding_records)
        run.ruleset_snapshot = ruleset_snapshot
        run.completed_at = datetime.now(timezone.utc)
        await self.repository.save_validation_run(run)
        await self.repository.create_event(
            CaseEventRecord(
                case_id=case_id,
                event_type="F03_VALIDATION_COMPLETED",
                event_data={
                    "validation_run_id": str(run.validation_run_id),
                    "form_instance_id": str(form_instance_id),
                    "passed_count": run.passed_count,
                    "warning_count": run.warning_count,
                    "failed_count": run.failed_count,
                },
                occurred_by_user_id=user.user_id,
                request_id=request_id,
            )
        )
        return await self.response(run)

    async def get(
        self, case_id: UUID, validation_run_id: UUID, user: User
    ) -> ValidationResponse:
        await self.valuation.get_case(case_id, user)
        record = await self.repository.get_validation_run(case_id, validation_run_id)
        if record is None:
            raise ResourceNotFoundError("檢核結果")
        return await self.response(record)

    async def response(self, run: ValidationRunRecord) -> ValidationResponse:
        findings = await self.repository.list_validation_findings(run.validation_run_id)
        snapshot = run.ruleset_snapshot or {}
        rule_snapshot = snapshot.get("rules", {})
        responses = []
        for finding in findings:
            rule = rule_snapshot.get(str(finding.validation_rule_id), {})
            responses.append(
                ValidationFindingResponse(
                    finding_id=finding.finding_id,
                    rule_code=rule.get("rule_code", str(finding.validation_rule_id)),
                    rule_version=f"{snapshot.get('rule_set_code', 'UNKNOWN')}:v{snapshot.get('version_no', '?')}",
                    field_path=finding.field_code,
                    severity=(
                        "WARNING" if finding.severity in {"LOW", "MEDIUM"} else "ERROR"
                    ),
                    actual_value=finding.actual_value,
                    expected_value=finding.expected_value,
                    message=finding.finding_message,
                    request_id=finding.request_id,
                    created_at=finding.created_at,
                )
            )
        return ValidationResponse(
            validation_run_id=run.validation_run_id,
            case_id=run.case_id,
            form_instance_id=run.form_instance_id,
            run_status=run.run_status,
            passed_count=run.passed_count,
            warning_count=run.warning_count,
            failed_count=run.failed_count,
            can_generate_report=run.failed_count == 0,
            ruleset_version=f"{snapshot.get('rule_set_code', 'UNKNOWN')}:v{snapshot.get('version_no', '?')}",
            correction_hints=[finding.message for finding in responses],
            findings=responses,
            request_id=run.request_id,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )

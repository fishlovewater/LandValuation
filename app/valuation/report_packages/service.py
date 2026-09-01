from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import AppError, ResourceNotFoundError
from app.valuation.models import FormInstanceRecord
from app.valuation.official_forms import OFFICIAL_SCHEMA_VERSION, OFFICIAL_FORM_TEMPLATES
from app.valuation.report_packages.repository import ReportPackageRepository
from app.valuation.report_packages.page_schemas import (
    F02DraftData,
    F02RFDraftData,
    S01DraftData,
)
from app.valuation.report_packages.requirements import (
    REPORT_COMPARISON_COMMERCIAL,
    REPORT_PACKAGES,
    REPORT_ROOT_FORM_CODE,
    REPORT_SCHEMA_VERSION,
    ReportPackageDefinition,
    get_report_definition,
)
from app.valuation.report_packages.schemas import (
    ReportComponentResponse,
    ReportPackageCreate,
    ReportPackageResponse,
    ReportPageRequirementResponse,
    ReportProgressResponse,
    ReportProgressSectionResponse,
    ReportRequirementsResponse,
    ReportSectionStatus,
    ReportType,
    ReportTypeResponse,
)
from app.valuation.schemas import CaseStatus, FormStatus
from app.valuation.service import ValuationService


COMPLETED_FORM_STATUSES = {
    FormStatus.READY.value,
    FormStatus.CHECKED.value,
    FormStatus.FINAL.value,
}


class ReportPackageService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ReportPackageRepository | None = None,
        valuation: ValuationService | None = None,
    ) -> None:
        self.repository = repository or ReportPackageRepository(session)
        self.valuation = valuation or ValuationService(session)

    @staticmethod
    def list_report_types() -> list[ReportTypeResponse]:
        return [ReportPackageService._type_response(item) for item in REPORT_PACKAGES.values()]

    @staticmethod
    def requirements(report_type: ReportType) -> ReportRequirementsResponse:
        definition = get_report_definition(report_type.value)
        if definition is None:
            raise ResourceNotFoundError("查估書類型")
        summary = ReportPackageService._type_response(definition)
        return ReportRequirementsResponse(
            **summary.model_dump(),
            pages=[
                ReportPageRequirementResponse(
                    code=page.code,
                    name=page.name,
                    kind=page.kind,
                    form_code=page.form_code,
                    document_type=page.document_type,
                )
                for page in definition.pages
            ],
        )

    @staticmethod
    def _type_response(definition: ReportPackageDefinition) -> ReportTypeResponse:
        return ReportTypeResponse(
            report_type=ReportType(definition.report_type),
            name=definition.name,
            land_use_type=definition.land_use_type,
            valuation_method=definition.valuation_method,
            page_count=len(definition.pages),
        )

    async def create(
        self,
        case_id: UUID,
        payload: ReportPackageCreate,
        user: User,
    ) -> ReportPackageResponse:
        case = await self.valuation._owned_editable_case(case_id, user)
        definition = get_report_definition(payload.report_type.value)
        if definition is None:
            raise ResourceNotFoundError("查估書類型")

        form_codes = tuple(
            page.form_code for page in definition.pages if page.form_code is not None
        )
        version_no = await self.repository.next_version(case_id, form_codes)
        component_ids = {form_code: uuid4() for form_code in form_codes}
        report_id = component_ids[REPORT_ROOT_FORM_CODE]
        component_map = {code: str(value) for code, value in component_ids.items()}

        records = [
            FormInstanceRecord(
                form_instance_id=component_ids[form_code],
                case_id=case_id,
                form_code=form_code,
                version_no=version_no,
                form_status=FormStatus.DRAFT.value,
                form_content={
                    "schema_version": REPORT_SCHEMA_VERSION,
                    "official_schema_version": OFFICIAL_SCHEMA_VERSION,
                    "template_source": OFFICIAL_FORM_TEMPLATES[
                        form_code
                    ].source_title,
                    "report_type": payload.report_type.value,
                    "report_id": str(report_id),
                    "report_version": version_no,
                    "page_code": form_code,
                    "components": component_map,
                    "page_schema_version": {
                        "S01": "s01-draft-v1",
                        "F02-RF": "f02-rf-draft-v1",
                        "F02": "f02-draft-v1",
                    }[form_code],
                    "data": {
                        "S01": S01DraftData,
                        "F02-RF": F02RFDraftData,
                        "F02": F02DraftData,
                    }[form_code]().model_dump(mode="json"),
                },
                prepared_date=payload.prepared_date,
                created_by_user_id=user.user_id,
                updated_by_user_id=user.user_id,
            )
            for form_code in form_codes
        ]
        created = await self.repository.create_forms(records)

        if case.case_status == CaseStatus.DRAFT.value:
            case.case_status = CaseStatus.PROCESSING.value
            case.updated_by_user_id = user.user_id

        return self._package_response(
            report_id=report_id,
            case_id=case_id,
            report_type=payload.report_type,
            version_no=version_no,
            prepared_date=payload.prepared_date,
            records=created,
        )

    async def get(
        self,
        case_id: UUID,
        report_id: UUID,
        user: User,
    ) -> ReportPackageResponse:
        await self.valuation.get_case(case_id, user)
        root = await self.repository.get_form(case_id, report_id)
        if root is None:
            raise ResourceNotFoundError("完整查估書")
        records = await self._load_components(case_id, root)
        return self._package_response(
            report_id=report_id,
            case_id=case_id,
            report_type=ReportType.REPORT_COMPARISON_COMMERCIAL,
            version_no=root.version_no,
            prepared_date=root.prepared_date,
            records=records,
        )

    async def progress(self, case_id: UUID, user: User) -> ReportProgressResponse:
        await self.valuation.get_case(case_id, user)
        definition = REPORT_PACKAGES[REPORT_COMPARISON_COMMERCIAL]
        root = await self.repository.latest_root(case_id)
        forms_by_code: dict[str, FormInstanceRecord] = {}
        if root is not None:
            forms_by_code = {
                record.form_code: record
                for record in await self._load_components(case_id, root)
            }
        document_types = await self.repository.active_document_types(case_id)

        sections: list[ReportProgressSectionResponse] = []
        blocking_errors: list[str] = []
        completed = 0
        for page in definition.pages:
            if page.form_code is not None:
                form = forms_by_code.get(page.form_code)
                if form is None:
                    status = ReportSectionStatus.MISSING
                elif form.form_status in COMPLETED_FORM_STATUSES:
                    status = ReportSectionStatus.COMPLETED
                else:
                    status = ReportSectionStatus.IN_PROGRESS
                section = ReportProgressSectionResponse(
                    code=page.code,
                    name=page.name,
                    status=status,
                    form_instance_id=(form.form_instance_id if form else None),
                )
            else:
                status = (
                    ReportSectionStatus.COMPLETED
                    if page.document_type in document_types
                    else ReportSectionStatus.MISSING
                )
                section = ReportProgressSectionResponse(
                    code=page.code,
                    name=page.name,
                    status=status,
                    document_type=page.document_type,
                )
            sections.append(section)
            if status == ReportSectionStatus.COMPLETED:
                completed += 1
            else:
                suffix = "MISSING" if status == ReportSectionStatus.MISSING else "INCOMPLETE"
                blocking_errors.append(f"{page.code}_{suffix}")

        rate = (
            Decimal(completed * 100) / Decimal(len(definition.pages))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return ReportProgressResponse(
            report_id=(root.form_instance_id if root else None),
            report_type=ReportType.REPORT_COMPARISON_COMMERCIAL,
            version_no=(root.version_no if root else None),
            completion_rate=f"{rate:.2f}",
            sections=sections,
            blocking_errors=blocking_errors,
        )

    async def _load_components(
        self, case_id: UUID, root: FormInstanceRecord
    ) -> list[FormInstanceRecord]:
        content = root.form_content if isinstance(root.form_content, dict) else {}
        if (
            root.form_code != REPORT_ROOT_FORM_CODE
            or content.get("report_type") != REPORT_COMPARISON_COMMERCIAL
            or content.get("report_id") != str(root.form_instance_id)
            or content.get("report_version") != root.version_no
        ):
            raise AppError(
                "REPORT_PACKAGE_CONFLICT",
                "查估書主表單的套件識別資料不一致",
                409,
            )
        raw_components = content.get("components")
        if not isinstance(raw_components, dict):
            raise AppError(
                "REPORT_COMPONENTS_MISSING",
                "查估書缺少組成表單識別資料",
                409,
            )
        expected_codes = {"S01", "F02-RF", "F02"}
        if set(raw_components) != expected_codes:
            raise AppError(
                "REPORT_COMPONENTS_INVALID",
                "查估書組成表單代碼不完整",
                409,
            )
        try:
            expected_ids = {code: UUID(str(value)) for code, value in raw_components.items()}
        except (ValueError, TypeError) as exc:
            raise AppError(
                "REPORT_COMPONENTS_INVALID",
                "查估書組成表單識別值格式錯誤",
                409,
            ) from exc
        records = await self.repository.get_forms(case_id, set(expected_ids.values()))
        by_code = {record.form_code: record for record in records}
        if len(records) != len(expected_codes) or set(by_code) != expected_codes:
            raise AppError(
                "REPORT_COMPONENTS_MISSING",
                "查估書組成表單不存在或不屬於此案件",
                409,
            )
        for code, expected_id in expected_ids.items():
            record = by_code[code]
            if (
                record.form_instance_id != expected_id
                or record.version_no != root.version_no
                or record.form_content.get("report_id") != str(root.form_instance_id)
            ):
                raise AppError(
                    "REPORT_COMPONENT_CONFLICT",
                    "查估書組成表單版本或關聯不一致",
                    409,
                )
        return [by_code[code] for code in ("S01", "F02-RF", "F02")]

    @staticmethod
    def _package_response(
        *,
        report_id: UUID,
        case_id: UUID,
        report_type: ReportType,
        version_no: int,
        prepared_date: date | None,
        records: list[FormInstanceRecord],
    ) -> ReportPackageResponse:
        by_code = {record.form_code: record for record in records}
        root = by_code[REPORT_ROOT_FORM_CODE]
        return ReportPackageResponse(
            report_id=report_id,
            case_id=case_id,
            report_type=report_type,
            version_no=version_no,
            prepared_date=prepared_date,
            components=[
                ReportComponentResponse(
                    code=code,
                    form_instance_id=by_code[code].form_instance_id,
                    form_status=by_code[code].form_status,
                )
                for code in ("S01", "F02-RF", "F02")
            ],
            created_at=root.created_at,
            updated_at=root.updated_at,
        )

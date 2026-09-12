from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.service import role_codes
from app.core.exceptions import AppError, PermissionDeniedError, ResourceNotFoundError
from app.valuation.models import CaseRecord, FormInstanceRecord, ParcelRecord, ValuationLocationRecord
from app.valuation.official_forms import blank_form_content
from app.valuation.repository import ValuationRepository
from app.valuation.requirements import FORM_REQUIREMENTS
from app.valuation.schemas import (
    CaseCreate,
    CaseWorkspaceUpdate,
    CaseStatus,
    CaseUpdate,
    FormCode,
    FormCreate,
    FormDraftUpdate,
    FormRequirementResponse,
    FormStatus,
    ParcelCreate,
    ParcelUpdate,
)

EDITABLE_CASE_STATUSES = {
    CaseStatus.DRAFT.value,
    CaseStatus.PROCESSING.value,
    CaseStatus.CORRECTION.value,
    CaseStatus.REVISION_REQUIRED.value,
}
PRIVILEGED_READ_ROLES = {"REVIEWER", "INSPECTOR"}


class ValuationService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ValuationRepository | None = None,
    ) -> None:
        self.repository = repository or ValuationRepository(session)

    @staticmethod
    def form_requirements() -> list[FormRequirementResponse]:
        return [
            ValuationService._requirement_response(definition)
            for definition in FORM_REQUIREMENTS.values()
        ]

    @staticmethod
    def form_requirement(form_code: FormCode) -> FormRequirementResponse:
        definition = FORM_REQUIREMENTS.get(form_code.value)
        if definition is None:
            raise ResourceNotFoundError("表單類型")
        return ValuationService._requirement_response(definition)

    @staticmethod
    def _requirement_response(definition) -> FormRequirementResponse:
        return FormRequirementResponse(
            form_type=definition.form_code,
            form_name=definition.form_name,
            required_fields=list(definition.required_fields),
            required_documents=list(definition.required_documents),
            optional_documents=list(definition.optional_documents),
            calculated_fields=list(definition.calculated_fields),
        )

    async def create_case(self, payload: CaseCreate, user: User) -> CaseRecord:
        values = payload.model_dump()
        record = CaseRecord(
            **values,
            case_status=CaseStatus.DRAFT.value,
            created_by_user_id=user.user_id,
            updated_by_user_id=user.user_id,
        )
        created = await self.repository.create_case(record)
        self.session.add(ValuationLocationRecord(case_id=created.case_id, display_order=1, label="地點 1"))
        await self.session.flush()
        return created

    async def bootstrap_case(
        self, payload: CaseCreate, user: User
    ) -> tuple[CaseRecord, FormInstanceRecord]:
        """Create a case and its initial F03 in the current DB transaction."""
        case = await self.create_case(payload, user)
        initial_form = await self.create_form(
            case.case_id,
            FormCreate(
                form_code=FormCode.F03,
                prepared_date=payload.valuation_base_date,
            ),
            user,
        )
        # create_form transitions a new case from DRAFT to PROCESSING. Return
        # the current ORM state so the caller never sees a stale DRAFT status.
        case = await self.get_case(case.case_id, user)
        return case, initial_form

    async def list_cases(
        self,
        user: User,
        *,
        case_status: CaseStatus | None,
        offset: int,
        limit: int,
    ) -> list[CaseRecord]:
        owner_id = None if role_codes(user) & PRIVILEGED_READ_ROLES else user.user_id
        return await self.repository.list_cases(
            owner_id=owner_id,
            case_status=case_status.value if case_status else None,
            offset=offset,
            limit=limit,
        )

    async def get_case(self, case_id: UUID, user: User) -> CaseRecord:
        record = await self._case_or_404(case_id)
        self._require_case_read(record, user)
        return record

    async def update_case(
        self, case_id: UUID, payload: CaseUpdate, user: User
    ) -> CaseRecord:
        record = await self._owned_editable_case(case_id, user)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(record, field, value)
        record.updated_by_user_id = user.user_id
        return await self.repository.save_case(record)

    async def update_case_workspace(
        self, case_id: UUID, payload: CaseWorkspaceUpdate, user: User
    ) -> CaseRecord:
        record = await self._owned_editable_case(case_id, user)
        if payload.confirm_basic_info and record.basic_info_confirmed_at is None:
            record.basic_info_confirmed_at = datetime.now(UTC)
            record.basic_info_confirmed_by_user_id = user.user_id

        if payload.last_workspace_stage is not None:
            if (
                payload.last_workspace_stage.value != "case"
                and record.basic_info_confirmed_at is None
                and not payload.confirm_basic_info
            ):
                raise AppError(
                    "CASE_BASIC_INFO_NOT_CONFIRMED",
                    "請先確認案件基本資料後再進入估價流程。",
                    409,
                )
            record.last_workspace_stage = payload.last_workspace_stage.value

        record.updated_by_user_id = user.user_id
        return await self.repository.save_case(record)

    async def archive_case(self, case_id: UUID, user: User) -> CaseRecord:
        record = await self._case_or_404(case_id, for_update=True)
        self._require_case_owner(record, user)
        if record.case_status == CaseStatus.ARCHIVED.value:
            return record
        record.case_status = CaseStatus.ARCHIVED.value
        record.updated_by_user_id = user.user_id
        return await self.repository.save_case(record)

    async def create_parcel(
        self, case_id: UUID, payload: ParcelCreate, user: User
    ) -> ParcelRecord:
        case = await self._owned_editable_case(case_id, user)
        await self._validate_source_document(case_id, payload.source_document_id)
        await self._validate_location(case_id, payload.location_id)
        record = ParcelRecord(case_id=case_id, **payload.model_dump())
        if case.case_status == CaseStatus.DRAFT.value:
            case.case_status = CaseStatus.PROCESSING.value
            case.updated_by_user_id = user.user_id
        return await self.repository.create_parcel(record)

    async def list_parcels(self, case_id: UUID, user: User) -> list[ParcelRecord]:
        await self.get_case(case_id, user)
        return await self.repository.list_parcels(case_id)

    async def update_parcel(
        self,
        case_id: UUID,
        parcel_id: UUID,
        payload: ParcelUpdate,
        user: User,
    ) -> ParcelRecord:
        await self._owned_editable_case(case_id, user)
        record = await self.repository.get_parcel(case_id, parcel_id)
        if record is None:
            raise ResourceNotFoundError("宗地")
        values = payload.model_dump(exclude_unset=True)
        if "source_document_id" in values:
            await self._validate_source_document(case_id, values["source_document_id"])
        if "location_id" in values:
            await self._validate_location(case_id, values["location_id"])
        for field, value in values.items():
            setattr(record, field, value)
        return await self.repository.save_parcel(record)

    async def create_form(
        self, case_id: UUID, payload: FormCreate, user: User
    ) -> FormInstanceRecord:
        case = await self._owned_editable_case(case_id, user)
        if payload.form_content:
            raise AppError(
                "FORM_CREATE_MUST_START_BLANK",
                "官方表單建立時必須使用後端空白結構；請建立後再透過草稿 API 填入已確認資料",
                422,
            )
        await self._validate_source_document(case_id, payload.source_document_id)
        version_no = await self.repository.next_form_version(
            case_id, payload.form_code.value
        )
        form_content = blank_form_content(payload.form_code.value)
        if payload.form_code.value in {"F01", "F04"}:
            from app.valuation.f01_f04_schemas import F01DraftData, F04DraftData

            model = F01DraftData if payload.form_code.value == "F01" else F04DraftData
            form_content["data"] = model().model_dump(mode="json")
        record = FormInstanceRecord(
            case_id=case_id,
            form_code=payload.form_code.value,
            version_no=version_no,
            form_status=FormStatus.DRAFT.value,
            form_content=form_content,
            prepared_date=payload.prepared_date,
            source_document_id=payload.source_document_id,
            created_by_user_id=user.user_id,
            updated_by_user_id=user.user_id,
        )
        if case.case_status == CaseStatus.DRAFT.value:
            case.case_status = CaseStatus.PROCESSING.value
            case.updated_by_user_id = user.user_id
        return await self.repository.create_form(record)

    async def list_forms(self, case_id: UUID, user: User) -> list[FormInstanceRecord]:
        await self.get_case(case_id, user)
        return await self.repository.list_forms(case_id)

    async def get_form(
        self, case_id: UUID, form_id: UUID, user: User
    ) -> FormInstanceRecord:
        await self.get_case(case_id, user)
        record = await self.repository.get_form(case_id, form_id)
        if record is None:
            raise ResourceNotFoundError("估價表")
        return record

    async def update_form_draft(
        self,
        case_id: UUID,
        form_id: UUID,
        payload: FormDraftUpdate,
        user: User,
    ) -> FormInstanceRecord:
        await self._owned_editable_case(case_id, user)
        record = await self.repository.get_form(case_id, form_id)
        if record is None:
            raise ResourceNotFoundError("估價表")
        if record.form_status != FormStatus.DRAFT.value:
            raise AppError(
                "FORM_STATE_CONFLICT",
                "只有草稿狀態的估價表可以修改",
                409,
            )
        values = payload.model_dump(exclude_unset=True)
        content = record.form_content if isinstance(record.form_content, dict) else {}
        if (
            "form_content" in values
            and record.form_code in {"S01", "F02-RF", "F02"}
            and content.get("report_type") == "REPORT_COMPARISON_COMMERCIAL"
        ):
            raise AppError(
                "REPORT_PAGE_API_REQUIRED",
                "整份查估書前三頁必須使用專用頁面 API，不可覆寫套件關聯資料",
                409,
            )
        if "source_document_id" in values:
            await self._validate_source_document(case_id, values["source_document_id"])
        if "location_id" in values:
            await self._validate_location(case_id, values["location_id"])
        for field, value in values.items():
            setattr(record, field, value)
        record.updated_by_user_id = user.user_id
        return await self.repository.save_form(record)

    async def submit_form(
        self, case_id: UUID, form_id: UUID, user: User
    ) -> FormInstanceRecord:
        await self._owned_editable_case(case_id, user)
        record = await self.repository.get_form(case_id, form_id)
        if record is None:
            raise ResourceNotFoundError("估價表")
        if record.form_status == FormStatus.READY.value:
            return record
        if record.form_status != FormStatus.DRAFT.value:
            raise AppError(
                "FORM_STATE_CONFLICT",
                "此估價表目前不可提交",
                409,
            )
        content = record.form_content if isinstance(record.form_content, dict) else {}
        if (
            record.form_code in {"S01", "F02-RF", "F02"}
            and content.get("report_type") == "REPORT_COMPARISON_COMMERCIAL"
        ):
            raise AppError(
                "REPORT_PAGE_VALIDATION_REQUIRED",
                "整份查估書前三頁不可使用通用提交繞過專用完整性、因素與計算檢核",
                409,
            )
        record.form_status = FormStatus.READY.value
        record.updated_by_user_id = user.user_id
        return await self.repository.save_form(record)

    async def _case_or_404(
        self, case_id: UUID, *, for_update: bool = False
    ) -> CaseRecord:
        record = await self.repository.get_case(case_id, for_update=for_update)
        if record is None:
            raise ResourceNotFoundError("案件")
        return record

    async def _owned_editable_case(self, case_id: UUID, user: User) -> CaseRecord:
        record = await self._case_or_404(case_id, for_update=True)
        self._require_case_owner(record, user)
        if record.case_status not in EDITABLE_CASE_STATUSES:
            raise AppError(
                "CASE_STATE_CONFLICT",
                "案件目前狀態不可修改",
                409,
            )
        return record

    @staticmethod
    def _require_case_read(record: CaseRecord, user: User) -> None:
        if record.created_by_user_id == user.user_id:
            return
        if role_codes(user) & PRIVILEGED_READ_ROLES:
            return
        raise PermissionDeniedError("沒有存取此案件的權限")

    @staticmethod
    def _require_case_owner(record: CaseRecord, user: User) -> None:
        if record.created_by_user_id != user.user_id:
            raise PermissionDeniedError("只有案件建立者可以修改此案件")

    async def _validate_location(self, case_id: UUID, location_id: UUID | None) -> None:
        if location_id is None:
            return
        location = await self.repository.session.scalar(
            select(ValuationLocationRecord).where(
                ValuationLocationRecord.case_id == case_id,
                ValuationLocationRecord.location_id == location_id,
                ValuationLocationRecord.is_active.is_(True),
            )
        )
        if location is None:
            raise AppError("VALUATION_LOCATION_NOT_FOUND", "指定的宗地地點不存在或已封存", 422)
    async def _validate_source_document(
        self, case_id: UUID, document_id: UUID | None
    ) -> None:
        if document_id is None:
            return
        if not await self.repository.document_belongs_to_case(case_id, document_id):
            raise AppError(
                "CROSS_CASE_REFERENCE",
                "來源文件不存在、已停用或不屬於此案件",
                422,
            )

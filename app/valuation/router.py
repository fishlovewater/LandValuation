from io import BytesIO
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.core.exceptions import AppError
from app.valuation.schemas import (
    CaseCreate,
    CaseResponse,
    CaseStatus,
    CaseUpdate,
    FormCode,
    FormCreate,
    FormDraftUpdate,
    FormRequirementResponse,
    OfficialFormTemplateResponse,
    OfficialFormulaPolicyResponse,
    FormResponse,
    ParcelCreate,
    ParcelResponse,
    ParcelUpdate,
)
from app.valuation.official_forms import (
    FORMULA_POLICY,
    all_template_contracts,
    template_contract,
)
from app.valuation.f03_schemas import (
    BenchmarkLandCreate,
    BenchmarkLandResponse,
    F03DraftResponse,
    F03DraftUpdate,
)
from app.valuation.f03_service import F03Service
from app.valuation.f01_f04_schemas import (
    F01DraftUpdate,
    F04DraftUpdate,
    OfficialFormDataResponse,
    OfficialFormValidationResponse,
)
from app.valuation.f01_f04_service import F01F04Service
from app.valuation.official_pdf_builder import (
    TEMPLATE_VERSION,
    build_official_form_pdf,
    coordinate_manifest,
)
from app.valuation.official_field_catalog import flatten_pdf_values
from app.valuation.pdf_errors import build_pdf_safely
from app.valuation.service import ValuationService

router = APIRouter()

CaseReader = Annotated[User, Depends(require_permissions("case.read"))]
CaseCreator = Annotated[User, Depends(require_permissions("case.create"))]
CaseEditor = Annotated[User, Depends(require_permissions("case.update"))]
ValuationReader = Annotated[User, Depends(require_permissions("valuation.read"))]
ValuationEditor = Annotated[User, Depends(require_permissions("valuation.update"))]


@router.get("/form-types", response_model=list[FormRequirementResponse])
async def list_form_types(user: ValuationReader) -> list[FormRequirementResponse]:
    del user
    return ValuationService.form_requirements()


@router.get(
    "/form-templates",
    response_model=list[OfficialFormTemplateResponse],
    summary="取得官方 PDF 對應的空白表單結構",
)
async def list_official_form_templates(
    user: ValuationReader,
) -> list[OfficialFormTemplateResponse]:
    del user
    return [OfficialFormTemplateResponse.model_validate(item) for item in all_template_contracts()]


@router.get(
    "/form-templates/formula-policy",
    response_model=OfficialFormulaPolicyResponse,
    summary="取得正式公式與來源政策",
)
async def get_official_formula_policy(
    user: ValuationReader,
) -> OfficialFormulaPolicyResponse:
    del user
    return OfficialFormulaPolicyResponse.model_validate(FORMULA_POLICY)


@router.get(
    "/form-templates/{form_type}",
    response_model=OfficialFormTemplateResponse,
    summary="取得指定官方空白表單結構",
)
async def get_official_form_template(
    form_type: FormCode,
    user: ValuationReader,
) -> OfficialFormTemplateResponse:
    del user
    return OfficialFormTemplateResponse.model_validate(template_contract(form_type.value))


@router.get(
    "/form-templates/{form_type}/coordinates",
    summary="取得官方 PDF 固定欄位座標",
)
async def get_official_form_coordinates(form_type: FormCode, user: ValuationReader):
    del user
    if form_type.value not in {"F01", "F02", "F03", "F04"}:
        raise AppError("OFFICIAL_PDF_FORM_UNSUPPORTED", "此表單沒有單頁官方 PDF 版型", 422)
    return coordinate_manifest(form_type.value)


@router.get(
    "/form-templates/{form_type}/blank-pdf",
    response_class=StreamingResponse,
    summary="下載重繪官方空白 PDF",
)
async def download_official_blank_pdf(form_type: FormCode, user: ValuationReader):
    del user
    pdf = build_pdf_safely(
        build_official_form_pdf,
        form_type.value,
        interactive_blank=True,
    )
    filename = f"{form_type.value}_official_blank.pdf"
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get(
    "/form-types/{form_type}/requirements",
    response_model=FormRequirementResponse,
)
async def get_form_requirements(
    form_type: FormCode,
    user: ValuationReader,
) -> FormRequirementResponse:
    del user
    return ValuationService.form_requirement(form_type)


@router.post(
    "/cases",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_case(
    payload: CaseCreate,
    session: DbSession,
    user: CaseCreator,
) -> CaseResponse:
    record = await ValuationService(session).create_case(payload, user)
    return CaseResponse.model_validate(record)


@router.get("/cases", response_model=list[CaseResponse])
async def list_cases(
    session: DbSession,
    user: CaseReader,
    case_status: CaseStatus | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[CaseResponse]:
    records = await ValuationService(session).list_cases(
        user,
        case_status=case_status,
        offset=offset,
        limit=limit,
    )
    return [CaseResponse.model_validate(record) for record in records]


@router.get("/cases/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    session: DbSession,
    user: CaseReader,
) -> CaseResponse:
    record = await ValuationService(session).get_case(case_id, user)
    return CaseResponse.model_validate(record)


@router.patch("/cases/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: UUID,
    payload: CaseUpdate,
    session: DbSession,
    user: CaseEditor,
) -> CaseResponse:
    record = await ValuationService(session).update_case(case_id, payload, user)
    return CaseResponse.model_validate(record)


@router.post("/cases/{case_id}/archive", response_model=CaseResponse)
async def archive_case(
    case_id: UUID,
    session: DbSession,
    user: CaseEditor,
) -> CaseResponse:
    record = await ValuationService(session).archive_case(case_id, user)
    return CaseResponse.model_validate(record)


@router.post(
    "/cases/{case_id}/parcels",
    response_model=ParcelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_parcel(
    case_id: UUID,
    payload: ParcelCreate,
    session: DbSession,
    user: CaseEditor,
) -> ParcelResponse:
    record = await ValuationService(session).create_parcel(case_id, payload, user)
    return ParcelResponse.model_validate(record)


@router.get("/cases/{case_id}/parcels", response_model=list[ParcelResponse])
async def list_parcels(
    case_id: UUID,
    session: DbSession,
    user: CaseReader,
) -> list[ParcelResponse]:
    records = await ValuationService(session).list_parcels(case_id, user)
    return [ParcelResponse.model_validate(record) for record in records]


@router.patch(
    "/cases/{case_id}/parcels/{parcel_id}",
    response_model=ParcelResponse,
)
async def update_parcel(
    case_id: UUID,
    parcel_id: UUID,
    payload: ParcelUpdate,
    session: DbSession,
    user: CaseEditor,
) -> ParcelResponse:
    record = await ValuationService(session).update_parcel(
        case_id, parcel_id, payload, user
    )
    return ParcelResponse.model_validate(record)


@router.post(
    "/cases/{case_id}/benchmark-lands",
    response_model=BenchmarkLandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_benchmark_land(
    case_id: UUID,
    payload: BenchmarkLandCreate,
    session: DbSession,
    user: CaseEditor,
) -> BenchmarkLandResponse:
    record = await F03Service(session).create_benchmark_land(case_id, payload, user)
    return BenchmarkLandResponse.model_validate(record)


@router.get(
    "/cases/{case_id}/benchmark-lands",
    response_model=list[BenchmarkLandResponse],
)
async def list_benchmark_lands(
    case_id: UUID,
    session: DbSession,
    user: CaseReader,
) -> list[BenchmarkLandResponse]:
    records = await F03Service(session).list_benchmark_lands(case_id, user)
    return [BenchmarkLandResponse.model_validate(record) for record in records]


@router.post(
    "/cases/{case_id}/forms",
    response_model=FormResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_form(
    case_id: UUID,
    payload: FormCreate,
    session: DbSession,
    user: ValuationEditor,
) -> FormResponse:
    record = await ValuationService(session).create_form(case_id, payload, user)
    return FormResponse.model_validate(record)


@router.get("/cases/{case_id}/forms", response_model=list[FormResponse])
async def list_forms(
    case_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> list[FormResponse]:
    records = await ValuationService(session).list_forms(case_id, user)
    return [FormResponse.model_validate(record) for record in records]


@router.get("/cases/{case_id}/forms/{form_id}", response_model=FormResponse)
async def get_form(
    case_id: UUID,
    form_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> FormResponse:
    record = await ValuationService(session).get_form(case_id, form_id, user)
    return FormResponse.model_validate(record)


@router.get(
    "/cases/{case_id}/forms/{form_id}/f03",
    response_model=F03DraftResponse,
)
async def get_f03_draft(
    case_id: UUID,
    form_id: UUID,
    session: DbSession,
    user: ValuationReader,
) -> F03DraftResponse:
    record = await F03Service(session).get_draft(case_id, form_id, user)
    return F03DraftResponse.model_validate(record)


@router.get(
    "/cases/{case_id}/forms/{form_id}/f01",
    response_model=OfficialFormDataResponse,
)
async def get_f01_draft(case_id: UUID, form_id: UUID, session: DbSession, user: ValuationReader):
    return await F01F04Service(session).get(case_id, form_id, "F01", user)


@router.patch(
    "/cases/{case_id}/forms/{form_id}/f01",
    response_model=OfficialFormDataResponse,
)
async def update_f01_draft(case_id: UUID, form_id: UUID, payload: F01DraftUpdate, session: DbSession, user: ValuationEditor):
    return await F01F04Service(session).update(case_id, form_id, "F01", payload, user)


@router.post(
    "/cases/{case_id}/forms/{form_id}/f01/calculate",
    response_model=OfficialFormDataResponse,
)
async def calculate_f01_draft(case_id: UUID, form_id: UUID, session: DbSession, user: ValuationEditor):
    return await F01F04Service(session).calculate(case_id, form_id, "F01", user)


@router.post(
    "/cases/{case_id}/forms/{form_id}/f01/validate",
    response_model=OfficialFormValidationResponse,
)
async def validate_f01_draft(case_id: UUID, form_id: UUID, session: DbSession, user: ValuationReader):
    return await F01F04Service(session).validate(case_id, form_id, "F01", user)


@router.get(
    "/cases/{case_id}/forms/{form_id}/f04",
    response_model=OfficialFormDataResponse,
)
async def get_f04_draft(case_id: UUID, form_id: UUID, session: DbSession, user: ValuationReader):
    return await F01F04Service(session).get(case_id, form_id, "F04", user)


@router.patch(
    "/cases/{case_id}/forms/{form_id}/f04",
    response_model=OfficialFormDataResponse,
)
async def update_f04_draft(case_id: UUID, form_id: UUID, payload: F04DraftUpdate, session: DbSession, user: ValuationEditor):
    return await F01F04Service(session).update(case_id, form_id, "F04", payload, user)


@router.post(
    "/cases/{case_id}/forms/{form_id}/f04/calculate",
    response_model=OfficialFormDataResponse,
)
async def calculate_f04_draft(case_id: UUID, form_id: UUID, session: DbSession, user: ValuationEditor):
    return await F01F04Service(session).calculate(case_id, form_id, "F04", user)


@router.post(
    "/cases/{case_id}/forms/{form_id}/f04/validate",
    response_model=OfficialFormValidationResponse,
)
async def validate_f04_draft(case_id: UUID, form_id: UUID, session: DbSession, user: ValuationReader):
    return await F01F04Service(session).validate(case_id, form_id, "F04", user)


@router.patch(
    "/cases/{case_id}/forms/{form_id}/f03",
    response_model=F03DraftResponse,
)
async def update_f03_draft(
    case_id: UUID,
    form_id: UUID,
    payload: F03DraftUpdate,
    session: DbSession,
    user: ValuationEditor,
) -> F03DraftResponse:
    record = await F03Service(session).update_draft(case_id, form_id, payload, user)
    return F03DraftResponse.model_validate(record)


@router.get(
    "/cases/{case_id}/forms/{form_id}/official-pdf",
    response_class=StreamingResponse,
    summary="依固定座標產生 F01～F04 PDF",
)
async def download_filled_official_pdf(
    case_id: UUID,
    form_id: UUID,
    session: DbSession,
    user: ValuationReader,
):
    form = await ValuationService(session).get_form(case_id, form_id, user)
    if form.form_code not in {"F01", "F02", "F03", "F04"}:
        raise AppError("OFFICIAL_PDF_FORM_UNSUPPORTED", "此表單沒有單頁官方 PDF 版型", 422)
    if form.form_code == "F03":
        draft = await F03Service(session).get_draft(case_id, form_id, user)
        values = F03DraftResponse.model_validate(draft).model_dump(mode="json")
    else:
        content = form.form_content if isinstance(form.form_content, dict) else {}
        values = content.get("data") or {}
    service = ValuationService(session)
    case = CaseResponse.model_validate(await service.get_case(case_id, user)).model_dump(mode="json")
    parcels = [
        ParcelResponse.model_validate(item).model_dump(mode="json")
        for item in await service.list_parcels(case_id, user)
    ]
    values = flatten_pdf_values(form.form_code, values, {**case, "parcels": parcels})
    pdf = build_pdf_safely(build_official_form_pdf, form.form_code, values)
    filename = f"{form.form_code}_{form.form_instance_id}_official.pdf"
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Official-Template-Version": TEMPLATE_VERSION,
            "X-Form-Status": form.form_status,
        },
    )


@router.patch("/cases/{case_id}/forms/{form_id}", response_model=FormResponse)
async def update_form_draft(
    case_id: UUID,
    form_id: UUID,
    payload: FormDraftUpdate,
    session: DbSession,
    user: ValuationEditor,
) -> FormResponse:
    record = await ValuationService(session).update_form_draft(
        case_id, form_id, payload, user
    )
    return FormResponse.model_validate(record)


@router.post(
    "/cases/{case_id}/forms/{form_id}/submit",
    response_model=FormResponse,
)
async def submit_form(
    case_id: UUID,
    form_id: UUID,
    session: DbSession,
    user: ValuationEditor,
) -> FormResponse:
    record = await ValuationService(session).submit_form(case_id, form_id, user)
    return FormResponse.model_validate(record)

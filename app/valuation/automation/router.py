from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import ValidationError

from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.core.exceptions import AppError
from app.storage.dependencies import Storage
from app.valuation.automation.schemas import (
    AutomatedConfirmRequest,
    AutomatedIntakeManifest,
    AutomatedWorkflowResponse,
    ManualFieldValuesRequest,
)
from app.valuation.automation.service import AutomatedWorkflowService


router = APIRouter()

INTAKE_MANIFEST_SWAGGER_EXAMPLE = """{
  "case": {
    "case_no": "TEST-ONLY-請改成真實案件編號",
    "case_title": "測試案件（請改成真實案件名稱）",
    "case_type": "土地徵收補償市價查估",
    "valuation_base_date": "2026-08-27",
    "city_code": "65000000",
    "district_code": "65000010",
    "land_use_type": "COMMERCIAL"
  },
  "parcels": [],
  "benchmark_lands": [],
  "prepared_date": "2026-08-27",
  "create_commercial_report": true,
  "category_overrides": {}
}"""

WorkflowEditor = Annotated[
    User,
    Depends(
        require_permissions(
            "case.create",
            "case.read",
            "valuation.update",
            "document.upload",
            "document.download",
        )
    ),
]


@router.post(
    "/auto-workflows/intake",
    response_model=AutomatedWorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="一次上傳並自動準備查估書草稿",
    description=(
        "登入後只需在一次請求中提供 intake_manifest_json 與所有來源檔案。"
        "系統會建立案件、宗地、F03、可用的商業用地三頁套件、保存 MinIO 原檔、"
        "執行 PDF/OCR 與整理待確認候選；不會自行確認資料。"
    ),
)
async def create_automated_intake(
    session: DbSession,
    storage: Storage,
    user: WorkflowEditor,
    intake_manifest_json: Annotated[
        str,
        Form(
            description=(
                "AutomatedIntakeManifest JSON；同一份 JSON 一次提供案件、可選宗地、"
                "比準地與檔名分類覆寫"
            ),
            examples=[INTAKE_MANIFEST_SWAGGER_EXAMPLE],
        ),
    ],
    files: Annotated[
        list[UploadFile],
        File(
            description="一次選取所有來源資料檔案",
            json_schema_extra={
                "items": {"type": "string", "format": "binary"}
            },
        ),
    ],
) -> AutomatedWorkflowResponse:
    try:
        manifest = AutomatedIntakeManifest.model_validate_json(intake_manifest_json)
    except ValidationError as exc:
        raise AppError(
            "INTAKE_MANIFEST_INVALID",
            "一次上傳的 intake manifest 格式錯誤",
            422,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    return await AutomatedWorkflowService(session, storage).intake(
        manifest,
        files,
        user,
    )


@router.get(
    "/cases/{case_id}/auto-workflow/review",
    response_model=AutomatedWorkflowResponse,
    summary="集中查看所有待確認資料與草稿下載位置",
)
async def review_automated_intake(
    case_id: UUID,
    session: DbSession,
    storage: Storage,
    user: WorkflowEditor,
) -> AutomatedWorkflowResponse:
    return await AutomatedWorkflowService(session, storage).review(case_id, user)


@router.post(
    "/cases/{case_id}/auto-workflow/confirm",
    response_model=AutomatedWorkflowResponse,
    summary="一次確認候選並自動套入可安全寫入的草稿欄位",
    description=(
        "只套用 request 中逐筆確認的候選。找不到、拒絕或無法安全對應的欄位保持空白；"
        "回應提供與原三頁／六頁版型相同的草稿 PDF 下載位置，並把確認後的三頁草稿"
        "另存至 MinIO generated 前綴。草稿不冒充已通過正式檢核的報告。"
    ),
)
async def confirm_automated_intake(
    case_id: UUID,
    payload: AutomatedConfirmRequest,
    session: DbSession,
    storage: Storage,
    user: WorkflowEditor,
) -> AutomatedWorkflowResponse:
    return await AutomatedWorkflowService(session, storage).confirm(
        case_id,
        payload,
        user,
    )


@router.post(
    "/cases/{case_id}/auto-workflow/manual-fields",
    response_model=AutomatedWorkflowResponse,
    summary="載入簡易前端手動補充欄位",
    description=(
        "保存使用者在 OCR／AI 候選確認區輸入的非空欄位。未填寫欄位保持空白，"
        "可部分載入；成功載入後會重新產生確認用 Excel。"
    ),
)
async def save_manual_fields(
    case_id: UUID,
    payload: ManualFieldValuesRequest,
    session: DbSession,
    storage: Storage,
    user: WorkflowEditor,
) -> AutomatedWorkflowResponse:
    return await AutomatedWorkflowService(session, storage).save_manual_fields(
        case_id,
        payload,
        user,
    )

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import AppError, ResourceNotFoundError
from app.storage.service import StorageService
from app.valuation.documents.repository import DocumentRepository
from app.valuation.extraction.provider import (
    DocumentExtractionProvider,
    XlsxExtractionProvider,
    build_document_extraction_provider,
)
from app.valuation.extraction.repository import ExtractionRepository
from app.valuation.extraction.schemas import (
    CandidateDecision,
    ExtractionConfirmRequest,
)
from app.valuation.models import DocumentExtractionRecord, ExtractedFieldRecord
from app.valuation.service import ValuationService


class ExtractionService:
    def __init__(
        self,
        session: AsyncSession,
        storage: StorageService,
        repository: ExtractionRepository | None = None,
        provider: DocumentExtractionProvider | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.repository = repository or ExtractionRepository(session)
        self.documents = DocumentRepository(session)
        self.valuation = ValuationService(session)
        self.provider = provider

    async def start(
        self, case_id: UUID, document_id: UUID, user: User
    ) -> tuple[DocumentExtractionRecord, list[ExtractedFieldRecord]]:
        await self.valuation._owned_editable_case(case_id, user)
        document = await self.documents.get(case_id, document_id)
        if document is None or not document.is_active:
            raise ResourceNotFoundError("啟用中的案件文件")
        mime_type = document.mime_type.lower()
        if mime_type == "application/pdf":
            provider = self.provider or build_document_extraction_provider(get_settings())
        elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            provider = self.provider or XlsxExtractionProvider()
        else:
            raise AppError(
                "DOCUMENT_EXTRACTION_FORMAT_UNSUPPORTED",
                "目前只支援 PDF 或 XLSX 文件擷取",
                422,
            )

        extraction = await self.repository.create_extraction(
            DocumentExtractionRecord(
                case_id=case_id,
                document_id=document_id,
                provider=provider.provider_name,
                extraction_status="PROCESSING",
                created_by_user_id=user.user_id,
            )
        )
        response = await self.storage.download(document.object_key)
        try:
            content = await run_in_threadpool(response.read)
        finally:
            response.close()
            response.release_conn()

        try:
            result = await provider.extract(content)
            extraction.provider = result.provider
            extraction.page_count = result.page_count
            extraction.extracted_text = result.text
            extraction.completed_at = datetime.now(UTC)
            if not result.text.strip():
                extraction.extraction_status = "FAILED"
                extraction.error_message = (
                    "Textract 沒有擷取到文字，需要人工輸入"
                    if result.provider == "TEXTRACT"
                    else (
                        "本機 OCR 沒有擷取到文字，需要人工輸入"
                        if result.provider == "LOCAL_OCR"
                        else (
                            "Excel 沒有可擷取內容，需要人工輸入"
                            if result.provider == "LOCAL_XLSX"
                            else "PDF 沒有可擷取文字，需要 OCR 或人工輸入"
                        )
                    )
                )
                await self.repository.save_extraction(extraction)
                return extraction, []

            extraction.extraction_status = "COMPLETED"
            candidates = [
                ExtractedFieldRecord(
                    case_id=case_id,
                    extraction_id=extraction.extraction_id,
                    document_id=document_id,
                    form_code=item.form_code,
                    field_name=item.field_name,
                    extracted_value=item.value,
                    confidence=item.confidence,
                    source_page=item.source_page,
                    source_text=item.source_text,
                    analysis_provider="XLSX_RULE" if result.provider == "LOCAL_XLSX" else "RULE",
                    prompt_version=(
                        "xlsx-comparison-target-v1"
                        if result.provider == "LOCAL_XLSX"
                        else None
                    ),
                    field_status="NEEDS_CONFIRMATION",
                )
                for item in result.candidates
            ]
            await self.repository.add_candidates(candidates)
            await self.repository.save_extraction(extraction)
            return extraction, candidates
        except AppError:
            raise
        except Exception as exc:
            extraction.extraction_status = "FAILED"
            extraction.error_message = f"文件文字擷取失敗：{type(exc).__name__}"
            extraction.completed_at = datetime.now(UTC)
            await self.repository.save_extraction(extraction)
            return extraction, []

    async def get_latest(
        self, case_id: UUID, document_id: UUID, user: User
    ) -> tuple[DocumentExtractionRecord, list[ExtractedFieldRecord]]:
        await self.valuation.get_case(case_id, user)
        extraction = await self.repository.latest_for_document(case_id, document_id)
        if extraction is None:
            raise ResourceNotFoundError("文件擷取結果")
        return extraction, await self.repository.list_candidates(
            extraction.extraction_id
        )

    async def confirm(
        self,
        case_id: UUID,
        document_id: UUID,
        payload: ExtractionConfirmRequest,
        user: User,
    ) -> tuple[DocumentExtractionRecord, list[ExtractedFieldRecord]]:
        await self.valuation._owned_editable_case(case_id, user)
        extraction = await self.repository.latest_for_document(case_id, document_id)
        if extraction is None or extraction.extraction_status != "COMPLETED":
            raise ResourceNotFoundError("可確認的文件擷取結果")

        seen: set[UUID] = set()
        for item in payload.confirmations:
            if item.extracted_field_id in seen:
                raise AppError("DUPLICATE_CONFIRMATION", "候選欄位不可重複確認", 422)
            seen.add(item.extracted_field_id)
            candidate = await self.repository.get_candidate(
                case_id,
                extraction.extraction_id,
                item.extracted_field_id,
            )
            if candidate is None:
                raise ResourceNotFoundError("候選欄位")
            if candidate.field_status == "APPLIED":
                raise AppError("FIELD_ALREADY_APPLIED", "已套用欄位不可重新確認", 409)

            candidate.confirmed_by_user_id = user.user_id
            candidate.confirmed_at = datetime.now(UTC)
            if item.decision == CandidateDecision.REJECT:
                candidate.field_status = "REJECTED"
                candidate.confirmed_value = None
            else:
                candidate.field_status = "CONFIRMED"
                candidate.confirmed_value = self._confirmed_value(
                    candidate.extracted_value,
                    item.corrected_value,
                )
            await self.repository.save_candidate(candidate)

        return extraction, await self.repository.list_candidates(
            extraction.extraction_id
        )

    @staticmethod
    def _confirmed_value(extracted: Any, corrected: Any | None) -> Any:
        return extracted if corrected is None else corrected

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
    CandidateValue,
    DocumentExtractionProvider,
    XlsExtractionProvider,
    XlsxExtractionProvider,
    build_document_extraction_provider,
)
from app.valuation.extraction.field_catalog import (
    F01_FIELD_ANALYSIS_FIELDS,
    F02_FIELD_ANALYSIS_FIELDS,
    F02_RF_FIELD_ANALYSIS_FIELDS,
    F03_FIELD_ANALYSIS_FIELDS,
    F04_FIELD_ANALYSIS_FIELDS,
    S01_FIELD_ANALYSIS_FIELDS,
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
        self,
        case_id: UUID,
        document_id: UUID,
        user: User,
        *,
        _skip_case_access: bool = False,
    ) -> tuple[DocumentExtractionRecord, list[ExtractedFieldRecord]]:
        if not _skip_case_access:
            await self.valuation._owned_editable_case(case_id, user)
        document = await self.documents.get(case_id, document_id)
        if document is None or not document.is_active:
            raise ResourceNotFoundError("啟用中的案件文件")
        mime_type = document.mime_type.lower()
        if mime_type == "application/pdf":
            provider = self.provider or build_document_extraction_provider(get_settings())
        elif mime_type == "application/vnd.ms-excel":
            provider = self.provider or XlsExtractionProvider()
        elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            provider = self.provider or XlsxExtractionProvider()
        else:
            raise AppError(
                "DOCUMENT_EXTRACTION_FORMAT_UNSUPPORTED",
                "目前只支援 PDF、XLS 或 XLSX 文件擷取",
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
            extraction.extraction_metadata = result.metadata
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
                            if result.provider in {"LOCAL_XLS", "LOCAL_XLSX"}
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
                    location_id=document.location_id,
                    document_id=document_id,
                    form_code=item.form_code,
                    field_name=item.field_name,
                    extracted_value=item.value,
                    confidence=item.confidence,
                    source_page=item.source_page,
                    source_text=item.source_text,
                    analysis_provider=(
                        "XLS_RULE"
                        if result.provider == "LOCAL_XLS"
                        else "XLSX_RULE"
                        if result.provider == "LOCAL_XLSX"
                        else "RULE"
                    ),
                    prompt_version=(
                        "xls-comparison-target-v1"
                        if result.provider == "LOCAL_XLS"
                        else "xlsx-comparison-target-v1"
                        if result.provider == "LOCAL_XLSX"
                        else None
                    ),
                    field_status="NEEDS_CONFIRMATION",
                )
                for item in self._validated_initial_candidates(
                    result.candidates,
                    extracted_text=result.text,
                )
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

    @staticmethod
    def _validated_initial_candidates(
        candidates: tuple[CandidateValue, ...],
        *,
        extracted_text: str | None = None,
    ) -> tuple[CandidateValue, ...]:
        """Keep OCR/XLSX rule candidates aligned with the official catalogs.

        Local OCR heuristics historically emitted several generic field names
        while defaulting their form to F03.  Reclassify the unambiguous names,
        canonicalize the F03 land-number alias, and drop anything that is not
        an exact catalog key.  AI analysis still handles the complete source
        text for all six forms after this inexpensive first pass.
        """

        catalogs = {
            "F01": F01_FIELD_ANALYSIS_FIELDS,
            "F02": F02_FIELD_ANALYSIS_FIELDS,
            "F02-RF": F02_RF_FIELD_ANALYSIS_FIELDS,
            "F03": F03_FIELD_ANALYSIS_FIELDS,
            "F04": F04_FIELD_ANALYSIS_FIELDS,
            "S01": S01_FIELD_ANALYSIS_FIELDS,
        }
        aliases = {
            # These are legacy heuristic labels, not catalog field names.
            "transaction_no": ("F01", "case_and_instance_refs"),
            "benchmark_land_no": ("F03", "land_no"),
        }
        unambiguous_form_by_field = {
            "transaction_total_price": "F01",
            **{
                field_name: "F02-RF"
                for field_name in F02_RF_FIELD_ANALYSIS_FIELDS
            },
        }
        normalized: list[CandidateValue] = []
        seen: set[tuple[str, str]] = set()
        if extracted_text is not None:
            # Share the same source-section routing as AI/Codex analysis.
            # Import lazily to keep the OCR provider independent of the AI
            # service at module import time.
            from app.valuation.extraction.field_analysis import _analysis_source_text

        for item in candidates:
            form_code = item.form_code
            field_name = item.field_name
            alias = aliases.get(field_name)
            if alias is not None:
                form_code, field_name = alias
            if field_name not in catalogs.get(form_code, {}):
                form_code = unambiguous_form_by_field.get(field_name, form_code)
            if field_name not in catalogs.get(form_code, {}):
                continue
            if extracted_text is not None:
                scoped_text = _analysis_source_text(extracted_text, form_code)
                if not scoped_text or item.source_text.strip() not in scoped_text:
                    continue
            key = (form_code, field_name)
            if key in seen:
                continue
            seen.add(key)
            if field_name == item.field_name and form_code == item.form_code:
                normalized.append(item)
            else:
                normalized.append(
                    CandidateValue(
                        field_name=field_name,
                        value=item.value,
                        confidence=item.confidence,
                        source_page=item.source_page,
                        source_text=item.source_text,
                        form_code=form_code,
                    )
                )
        return tuple(normalized)

    async def get_latest(
        self,
        case_id: UUID,
        document_id: UUID,
        user: User,
        *,
        _skip_case_access: bool = False,
    ) -> tuple[DocumentExtractionRecord, list[ExtractedFieldRecord]]:
        if not _skip_case_access:
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
        *,
        _skip_case_access: bool = False,
        _apply_for_review: bool = False,
    ) -> tuple[DocumentExtractionRecord, list[ExtractedFieldRecord]]:
        if not _skip_case_access:
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
                # A user may reopen an applied candidate from the review
                # workbench and submit a corrected value. The next apply
                # operation will replace the previous value on the formal
                # draft and mark this candidate applied again.
                candidate.applied_form_instance_id = None
                candidate.applied_at = None

            candidate.confirmed_by_user_id = user.user_id
            candidate.confirmed_at = datetime.now(UTC)
            if item.decision == CandidateDecision.REJECT:
                candidate.field_status = "REJECTED"
                candidate.confirmed_value = None
            else:
                candidate.field_status = "APPLIED" if _apply_for_review else "CONFIRMED"
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

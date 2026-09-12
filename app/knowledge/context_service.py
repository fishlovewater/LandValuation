from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.service import permission_codes
from app.core.exceptions import PermissionDeniedError
from app.history.service import HistoryService
from app.knowledge.case_repository import CaseContextRepository
from app.knowledge.policy import CASE_READ_PERMISSION, may_view_review_result
from app.knowledge.schemas import CaseAssistantContextResponse
from app.valuation.service import ValuationService


DOCUMENT_DOWNLOAD_PERMISSION = "document.download"


async def load_authorized_case_context(
    session: AsyncSession,
    user: User,
    case_id: UUID,
    *,
    workspace: str | None = None,
) -> CaseAssistantContextResponse:
    """Return existing Valuation/Review data without changing either subsystem.

    The returned object is deliberately structured context, not a knowledge
    citation.  A caller must not present it as if it were a statute or MinIO
    source.  This keeps case facts auditable while the knowledge answer itself
    remains grounded in document citations.
    """

    permissions = permission_codes(user)
    if CASE_READ_PERMISSION not in permissions:
        raise PermissionDeniedError("沒有查看案件情境的權限")

    normalized_workspace = (workspace or "").strip().lower()

    if normalized_workspace == "history":
        # History has its own role/module visibility policy. Reuse it so a case
        # that is legally visible in History remains visible to the assistant,
        # while Review-only documents stay hidden from Valuation-only users.
        history_detail = await HistoryService(session).detail(case_id, user)
        repository = CaseContextRepository(session)
        case = await repository.case_brief(case_id)
        documents = [
            {
                "document_id": document.document_id,
                "document_type": document.document_type,
                "file_name": document.file_name,
                "content_type": document.content_type,
                "version_no": document.version_no,
                "uploaded_at": document.created_at,
                "file_size_bytes": document.file_size_bytes,
            }
            for document in history_detail.documents
            if document.is_active
        ]
        document_access = True
        document_access_note = "已依案件歷程權限提供可調閱的有效文件。"
        review_access = history_detail.permissions.can_view_review
        review_access_note = (
            "已依案件歷程權限提供審查資料。"
            if review_access
            else "目前帳號沒有查看審查結果的權限。"
        )
    else:
        # Valuation/Review reuse the canonical case-read policy before any case
        # facts or document metadata enter the assistant context.
        await ValuationService(session).get_case(case_id, user)
        repository = CaseContextRepository(session)
        case = await repository.case_brief(case_id)
        document_access = DOCUMENT_DOWNLOAD_PERMISSION in permissions
        documents = await repository.active_documents(case_id) if document_access else []
        document_access_note = (
            "已提供目前帳號可查看的有效案件文件。"
            if document_access
            else "目前帳號沒有查看案件文件的權限。"
        )
        review_access = may_view_review_result(user)
        review_access_note = (
            "已依既有 review.read 權限提供最新審查結果。"
            if review_access
            else "目前帳號沒有查看審查結果的權限。"
        )

    return CaseAssistantContextResponse(
        case=case,
        document_access=document_access,
        document_access_note=document_access_note,
        documents=documents,
        review_access=review_access,
        review_access_note=review_access_note,
        latest_review=(await repository.latest_review(case_id) if review_access else None),
    )

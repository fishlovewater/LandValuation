from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.service import permission_codes
from app.core.exceptions import PermissionDeniedError
from app.knowledge.case_repository import CaseContextRepository
from app.knowledge.policy import CASE_READ_PERMISSION, may_view_review_result
from app.knowledge.schemas import CaseAssistantContextResponse


DOCUMENT_DOWNLOAD_PERMISSION = "document.download"


async def load_authorized_case_context(
    session: AsyncSession,
    user: User,
    case_id: UUID,
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

    repository = CaseContextRepository(session)
    case = await repository.case_brief(case_id)
    document_access = DOCUMENT_DOWNLOAD_PERMISSION in permissions
    documents = await repository.active_documents(case_id) if document_access else []
    document_access_note = (
        "已提供目前帳號可查看的有效案件文件。"
        if document_access
        else "目前帳號沒有查看案件文件的權限。"
    )
    if not may_view_review_result(user):
        return CaseAssistantContextResponse(
            case=case,
            document_access=document_access,
            document_access_note=document_access_note,
            documents=documents,
            review_access=False,
            review_access_note="目前帳號沒有查看審查結果的權限。",
        )
    return CaseAssistantContextResponse(
        case=case,
        document_access=document_access,
        document_access_note=document_access_note,
        documents=documents,
        review_access=True,
        review_access_note="已依既有 review.read 權限提供最新審查結果。",
        latest_review=await repository.latest_review(case_id),
    )

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import KnowledgeChunk, KnowledgeDocument
from app.knowledge.service import RetrievedKnowledge


class KnowledgeRepository:
    """Loads authorized knowledge metadata; router policy enforces reader access."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def retrieval_candidates(
        self,
        *,
        as_of_date: date | None,
        document_types: list[str],
        candidate_limit: int = 200,
    ) -> list[RetrievedKnowledge]:
        statement = (
            select(KnowledgeDocument, KnowledgeChunk)
            .join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.document_id)
            .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeChunk.chunk_no)
            .limit(candidate_limit)
        )
        if as_of_date is not None:
            statement = statement.where(
                (KnowledgeDocument.effective_from.is_(None))
                | (KnowledgeDocument.effective_from <= as_of_date),
                (KnowledgeDocument.effective_to.is_(None))
                | (KnowledgeDocument.effective_to >= as_of_date),
            )
        if document_types:
            statement = statement.where(KnowledgeDocument.document_type.in_(document_types))
        rows = (await self.session.execute(statement)).all()
        return [RetrievedKnowledge(document=document, chunk=chunk) for document, chunk in rows]

    async def documents_by_object_key(self) -> dict[str, KnowledgeDocument]:
        """Existing metadata is optional for runtime MinIO discovery."""

        documents = await self.session.scalars(select(KnowledgeDocument))
        return {document.object_key: document for document in documents}

    async def knowledge_document(self, document_id):
        """Return a knowledge source regardless of extraction or publication status."""

        return await self.session.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id)
        )

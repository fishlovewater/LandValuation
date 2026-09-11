from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import (
    KnowledgeChunk,
    KnowledgeConversationMessageRecord,
    KnowledgeConversationRecord,
    KnowledgeDocument,
)
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
        candidate_limit: int = 1000,
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

    async def create_conversation(
        self,
        *,
        user_id: UUID,
        provider: str,
        model_id: str | None,
        title: str = "新對話",
    ) -> KnowledgeConversationRecord:
        record = KnowledgeConversationRecord(
            user_id=user_id,
            title=title,
            provider=provider,
            model_id=model_id,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_conversation(
        self, conversation_id: UUID, user_id: UUID
    ) -> KnowledgeConversationRecord | None:
        return await self.session.scalar(
            select(KnowledgeConversationRecord).where(
                KnowledgeConversationRecord.conversation_id == conversation_id,
                KnowledgeConversationRecord.user_id == user_id,
                KnowledgeConversationRecord.status == "ACTIVE",
            )
        )

    async def list_conversations(
        self, user_id: UUID, *, limit: int = 30
    ) -> list[KnowledgeConversationRecord]:
        return list(
            (
                await self.session.scalars(
                    select(KnowledgeConversationRecord)
                    .where(
                        KnowledgeConversationRecord.user_id == user_id,
                        KnowledgeConversationRecord.status == "ACTIVE",
                    )
                    .order_by(KnowledgeConversationRecord.updated_at.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def list_conversation_messages(
        self, conversation_id: UUID, *, limit: int = 60
    ) -> list[KnowledgeConversationMessageRecord]:
        rows = list(
            (
                await self.session.scalars(
                    select(KnowledgeConversationMessageRecord)
                    .where(
                        KnowledgeConversationMessageRecord.conversation_id
                        == conversation_id
                    )
                    .order_by(KnowledgeConversationMessageRecord.message_no.desc())
                    .limit(limit)
                )
            ).all()
        )
        rows.reverse()
        return rows

    async def add_conversation_message(
        self,
        conversation: KnowledgeConversationRecord,
        *,
        role: str,
        content: str,
        response_payload: dict | None = None,
    ) -> KnowledgeConversationMessageRecord:
        latest = await self.session.scalar(
            select(func.max(KnowledgeConversationMessageRecord.message_no)).where(
                KnowledgeConversationMessageRecord.conversation_id
                == conversation.conversation_id
            )
        )
        record = KnowledgeConversationMessageRecord(
            conversation_id=conversation.conversation_id,
            message_no=(latest or 0) + 1,
            role=role,
            content=content,
            model_name=conversation.model_id if role == "ASSISTANT" else None,
            response_payload=response_payload or {},
        )
        self.session.add(record)
        conversation.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def rename_conversation_if_new(
        self, conversation: KnowledgeConversationRecord, question: str
    ) -> None:
        if conversation.title != "新對話":
            return
        title = " ".join(question.strip().split())[:60]
        if title:
            conversation.title = title
            conversation.updated_at = datetime.now(UTC)
            await self.session.flush()

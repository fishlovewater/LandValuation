from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.auth.models import User
from app.core.security import hash_password
from app.db.session import AsyncSessionFactory
from app.knowledge.repository import KnowledgeRepository


@pytest.mark.asyncio
async def test_knowledge_conversation_persists_history_and_is_user_scoped() -> None:
    now = datetime.now(UTC)
    owner_id = uuid4()
    other_id = uuid4()

    async with AsyncSessionFactory() as session:
        async with session.begin():
            for user_id, prefix in ((owner_id, "owner"), (other_id, "other")):
                session.add(
                    User(
                        user_id=user_id,
                        username=f"knowledge-{prefix}-{user_id.hex[:8]}",
                        email=f"knowledge-{prefix}-{user_id.hex[:8]}@example.test",
                        password_hash=hash_password("integration-password-123"),
                        display_name=f"Knowledge {prefix}",
                        is_active=True,
                        last_login_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            await session.flush()

            repository = KnowledgeRepository(session)
            conversation = await repository.create_conversation(
                user_id=owner_id,
                provider="ollama",
                model_id="qwen3.5:latest",
            )
            assert conversation.title == "新對話"
            assert conversation.provider == "ollama"

            await repository.add_conversation_message(
                conversation,
                role="USER",
                content="土地徵收補償市價查估的依據是什麼？",
            )
            await repository.rename_conversation_if_new(
                conversation,
                "土地徵收補償市價查估的依據是什麼？",
            )
            await repository.add_conversation_message(
                conversation,
                role="ASSISTANT",
                content="請依可核對來源確認查估依據。",
                response_payload={"answer_status": "EVIDENCE_ONLY"},
            )

            listed = await repository.list_conversations(owner_id)
            assert [item.conversation_id for item in listed] == [conversation.conversation_id]
            assert listed[0].title.startswith("土地徵收補償市價查估")

            messages = await repository.list_conversation_messages(conversation.conversation_id)
            assert [(item.message_no, item.role) for item in messages] == [
                (1, "USER"),
                (2, "ASSISTANT"),
            ]
            assert messages[1].response_payload == {"answer_status": "EVIDENCE_ONLY"}
            assert messages[1].model_name == "qwen3.5:latest"

            assert await repository.get_conversation(conversation.conversation_id, owner_id) is not None
            assert await repository.get_conversation(conversation.conversation_id, other_id) is None

        await session.rollback()

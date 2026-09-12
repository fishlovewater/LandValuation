from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.ai_assistant.schemas import (
    AssistantHistoryMessageResponse,
    AssistantMessageRequest,
    AssistantMessageResponse,
    AssistantProgressResponse,
    AssistantQuestionRequest,
    AssistantQuestionResponse,
    AssistantSessionCreate,
    AssistantSessionResponse,
)
from app.ai_assistant.service import AssistantService
from app.auth.dependencies import DbSession, require_permissions
from app.auth.models import User
from app.storage.dependencies import Storage

router = APIRouter()

AssistantUser = Annotated[
    User,
    Depends(require_permissions("assistant.use", "valuation.read")),
]
AssistantQuestionUser = Annotated[
    User,
    Depends(
        require_permissions(
            "assistant.use",
            "valuation.read",
        )
    ),
]


def request_uuid(request: Request) -> UUID | None:
    try:
        return UUID(str(request.state.request_id))
    except (ValueError, TypeError, AttributeError):
        return None


@router.post(
    "/sessions",
    response_model=AssistantSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assistant_session(
    payload: AssistantSessionCreate,
    session: DbSession,
    user: AssistantUser,
) -> AssistantSessionResponse:
    record = await AssistantService(session).create_session(payload, user)
    return AssistantSessionResponse.model_validate(record)


@router.get("/sessions/{session_id}", response_model=AssistantSessionResponse)
async def get_assistant_session(
    session_id: UUID,
    session: DbSession,
    user: AssistantUser,
) -> AssistantSessionResponse:
    record = await AssistantService(session).get_session(session_id, user)
    return AssistantSessionResponse.model_validate(record)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[AssistantHistoryMessageResponse],
)
async def get_assistant_messages(
    session_id: UUID,
    session: DbSession,
    user: AssistantUser,
) -> list[AssistantHistoryMessageResponse]:
    service = AssistantService(session)
    record = await service.get_session(session_id, user)
    rows = await service.repository.list_messages(record.assistant_session_id)
    return [
        AssistantHistoryMessageResponse(
            assistant_message_id=row.assistant_message_id,
            message_no=row.message_no,
            role=row.role,
            content=row.content,
            response_payload=row.response_payload or {},
            created_at=row.created_at,
        )
        for row in rows
        if row.role in {"USER", "ASSISTANT"}
    ]


@router.get(
    "/sessions/{session_id}/progress",
    response_model=AssistantProgressResponse,
)
async def get_assistant_progress(
    session_id: UUID,
    session: DbSession,
    user: AssistantUser,
) -> AssistantProgressResponse:
    return await AssistantService(session).progress(session_id, user)


@router.post(
    "/sessions/{session_id}/questions",
    response_model=AssistantQuestionResponse,
)
async def ask_assistant_question(
    session_id: UUID,
    payload: AssistantQuestionRequest,
    session: DbSession,
    storage: Storage,
    user: AssistantQuestionUser,
) -> AssistantQuestionResponse:
    return await AssistantService(session, storage=storage).ask_question(
        session_id,
        payload,
        user,
        storage,
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=AssistantMessageResponse,
)
async def send_assistant_message(
    session_id: UUID,
    payload: AssistantMessageRequest,
    request: Request,
    session: DbSession,
    storage: Storage,
    user: AssistantUser,
) -> AssistantMessageResponse:
    record, reply, progress, tools = await AssistantService(
        session, storage=storage
    ).send_message(
        session_id,
        payload,
        user,
        request_uuid(request),
    )
    return AssistantMessageResponse(
        session=AssistantSessionResponse.model_validate(record),
        reply=reply,
        progress=progress,
        tools=tools,
    )

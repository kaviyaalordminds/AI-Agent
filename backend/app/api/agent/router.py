import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.agents.orchestrator import record_unavailable_turn, run_chat_turn
from app.database.session import SessionLocal, get_db
from app.integrations.claude.errors import ProviderNotConfiguredError, ProviderRequestError
from app.integrations.claude.factory import get_claude_provider, get_claude_status
from app.models.conversation import AgentMode, Conversation
from app.models.project import Project
from app.models.user import User
from app.schemas.agent import (
    ClaudeStatusOut,
    ConversationDetailOut,
    ConversationOut,
    CreateConversationRequest,
    MessageOut,
    SendMessageRequest,
    UpdateConversationRequest,
)
from app.schemas.auth import MessageResponse
from app.security.sessions import get_current_user, require_csrf

logger = logging.getLogger("api.agent")
router = APIRouter(prefix="/agent", tags=["agent"])


def _get_owned_conversation(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


def _to_out(conversation: Conversation) -> ConversationOut:
    out = ConversationOut.model_validate(conversation)
    out.project_name = conversation.project.name if conversation.project else None
    return out


@router.get("/status", response_model=ClaudeStatusOut)
def claude_status():
    return ClaudeStatusOut.model_validate(get_claude_status().__dict__)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    project_id: uuid.UUID | None = Query(default=None),
    mode: AgentMode | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # joinedload avoids an N+1 (one SELECT per row) that _to_out's
    # conversation.project.name lazy-load would otherwise trigger.
    query = db.query(Conversation).options(joinedload(Conversation.project)).filter(Conversation.user_id == user.id)
    if project_id is not None:
        query = query.filter(Conversation.project_id == project_id)
    if mode is not None:
        query = query.filter(Conversation.mode == mode)
    conversations = query.order_by(Conversation.updated_at.desc()).all()
    return [_to_out(c) for c in conversations]


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: CreateConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    if payload.project_id is not None:
        owned_project = (
            db.query(Project)
            .filter(Project.id == payload.project_id, Project.user_id == user.id)
            .first()
        )
        if owned_project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    conversation = Conversation(
        user_id=user.id,
        project_id=payload.project_id,
        mode=payload.mode,
        title=payload.title or "New conversation",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _to_out(conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    conversation = _get_owned_conversation(db, user, conversation_id)
    out = ConversationDetailOut.model_validate(conversation)
    out.project_name = conversation.project.name if conversation.project else None
    out.messages = [MessageOut.model_validate(m) for m in conversation.messages]
    return out


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: uuid.UUID,
    payload: UpdateConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    conversation = _get_owned_conversation(db, user, conversation_id)
    conversation.title = payload.title
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _to_out(conversation)


@router.delete("/conversations/{conversation_id}", response_model=MessageResponse)
def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    conversation = _get_owned_conversation(db, user, conversation_id)
    db.delete(conversation)
    db.commit()
    return MessageResponse(message="Conversation deleted.")


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    # Ownership check uses the request-scoped session — fine, since it
    # completes before the response is returned.
    conversation = _get_owned_conversation(db, user, conversation_id)

    try:
        provider = get_claude_provider()
    except ProviderNotConfiguredError as exc:
        # The user's message must not be lost just because the assistant
        # can't reply — persist it (and the resulting failed turn) before
        # rejecting the request.
        record_unavailable_turn(db, conversation, payload.content, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    async def event_stream():
        # The request-scoped `db` dependency is closed by the time a
        # StreamingResponse body iterator actually runs (FastAPI returns
        # the response and tears down dependencies before streaming the
        # body), so a fresh, stream-lifetime session is required here.
        stream_db = SessionLocal()
        try:
            conversation = (
                stream_db.query(Conversation).filter(Conversation.id == conversation_id).first()
            )
            async for delta in run_chat_turn(stream_db, conversation, provider, payload.content):
                yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except ProviderRequestError as exc:
            logger.warning("Claude request failed for conversation %s: %s", conversation_id, exc)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            stream_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

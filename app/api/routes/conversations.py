from fastapi import APIRouter, Depends, HTTPException

from app.domain.interfaces.chat_history import ChatHistory
from app.core.dependencies import get_chat_history

router = APIRouter()


@router.get("/api/conversations/{session_id}")
def get_conversation(
    session_id: str,
    chat_history: ChatHistory = Depends(get_chat_history),
):
    """Retorna todas as mensagens de uma sessão de chat.

    Response: ``{"session_id": "...", "messages": [{"role": "...", "content": "...", "timestamp": "..."}]}``
    """
    messages = chat_history.get_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Sessão não encontrada ou vazia")
    return {"session_id": session_id, "messages": messages}

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class SessionBase(BaseModel):
    campaign_id: UUID
    character_id: UUID
    title: Optional[str] = None


class SessionCreate(SessionBase):
    pass


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[SessionStatus] = None
    summary: Optional[str] = None
    game_state: Optional[Dict[str, Any]] = None
    current_location: Optional[str] = None


class SessionResponse(SessionBase):
    id: UUID
    status: SessionStatus
    summary: Optional[str]
    game_state: Dict[str, Any]
    current_location: Optional[str]
    active_combat_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageBase(BaseModel):
    content: str


class MessageCreate(MessageBase):
    pass


class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: MessageRole
    content: str
    sequence: int
    tool_calls: Optional[List[Dict[str, Any]]]
    tool_results: Optional[List[Dict[str, Any]]]
    extra_data: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class SessionWithMessages(SessionResponse):
    messages: List[MessageResponse]


class PlayerAction(BaseModel):
    """Player input during a game session."""
    action: str = Field(..., min_length=1)
    context: Optional[Dict[str, Any]] = None


class DMResponse(BaseModel):
    """DM response with optional tool results."""
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    game_state_updates: Optional[Dict[str, Any]] = None

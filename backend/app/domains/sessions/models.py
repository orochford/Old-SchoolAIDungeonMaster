from sqlalchemy import Column, String, Text, ForeignKey, Enum as SQLEnum, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base
from app.shared.base_model import BaseModel


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Session(Base, BaseModel):
    """Game session with conversation history and state."""

    __tablename__ = "sessions"

    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)

    title = Column(String(200))
    status = Column(
        String(20),  # Database uses VARCHAR, not enum
        default="active",
        nullable=False,
    )

    # Session summary (for display and context)
    summary = Column(Text)

    # Current game state snapshot
    game_state = Column(JSONB, default={})

    # Adventure state tracking (scenes, plot threads, NPCs, etc.)
    adventure_state = Column(JSONB, default={})

    # Location within the game world
    current_location = Column(String(200))

    # Active combat encounter (if any)
    active_combat_id = Column(UUID(as_uuid=True), ForeignKey("combat_encounters.id"), nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="sessions")
    messages = relationship("ConversationMessage", back_populates="session", order_by="ConversationMessage.sequence")
    journal_entries = relationship("JournalEntry", back_populates="session")


class ConversationMessage(Base, BaseModel):
    """Session message history for context."""

    __tablename__ = "conversation_messages"

    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)

    role = Column(SQLEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    sequence = Column(Integer, nullable=False)

    # Tool calls and results
    tool_calls = Column(JSONB)
    tool_results = Column(JSONB)

    # Extra data (token count, model used, etc.)
    extra_data = Column(JSONB, default={})

    # Relationships
    session = relationship("Session", back_populates="messages")

from sqlalchemy import Column, String, Text, Boolean, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base
from app.shared.base_model import BaseModel


class CampaignStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class RPGSystem(Base, BaseModel):
    """Registry of supported RPG systems."""

    __tablename__ = "rpg_systems"

    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    version = Column(String(50))
    is_active = Column(Boolean, default=True)

    # System-specific configuration
    config = Column(JSONB, default={})

    # Relationships
    campaigns = relationship("Campaign", back_populates="rpg_system")
    characters = relationship("Character", back_populates="rpg_system")
    pdf_documents = relationship("PDFDocument", back_populates="rpg_system")


class Campaign(Base, BaseModel):
    """Game campaign with settings and state."""

    __tablename__ = "campaigns"

    name = Column(String(200), nullable=False)
    description = Column(Text)
    status = Column(
        SQLEnum(CampaignStatus),
        default=CampaignStatus.ACTIVE,
        nullable=False,
    )

    # Foreign keys
    rpg_system_id = Column(UUID(as_uuid=True), ForeignKey("rpg_systems.id"), nullable=False)

    # Adventure module being used for this campaign (optional)
    adventure_document_id = Column(UUID(as_uuid=True), ForeignKey("pdf_documents.id"), nullable=True)

    # Campaign state (locations, flags, world state)
    game_state = Column(JSONB, default={})

    # Campaign settings (house rules, difficulty, etc.)
    settings = Column(JSONB, default={})

    # Relationships
    rpg_system = relationship("RPGSystem", back_populates="campaigns")
    adventure_document = relationship("PDFDocument", foreign_keys=[adventure_document_id])
    characters = relationship("Character", back_populates="campaign")
    sessions = relationship("Session", back_populates="campaign")
    journal_entries = relationship("JournalEntry", back_populates="campaign")
    world_locations = relationship("WorldLocation", back_populates="campaign")
    consequences = relationship("WorldConsequence", back_populates="campaign")
    calendar = relationship("CampaignCalendar", back_populates="campaign", uselist=False)


# Default calendar configuration for fantasy settings
DEFAULT_CALENDAR_CONFIG = {
    "months": [
        {"name": "Deepwinter", "days": 30},
        {"name": "Thawmoon", "days": 30},
        {"name": "Seedsow", "days": 31},
        {"name": "Rainmoot", "days": 30},
        {"name": "Highsun", "days": 31},
        {"name": "Summertide", "days": 30},
        {"name": "Harvestmoon", "days": 31},
        {"name": "Leaffall", "days": 30},
        {"name": "Frostfall", "days": 30},
        {"name": "Darknight", "days": 31},
        {"name": "Snowmelt", "days": 30},
        {"name": "Yearsend", "days": 30},
    ],
    "moon_cycle_days": 28,
    "seasons": {
        "winter": [1, 2, 11, 12],
        "spring": [3, 4],
        "summer": [5, 6, 7],
        "autumn": [8, 9, 10],
    },
    "hours_per_day": 24,
}


class CampaignCalendar(Base, BaseModel):
    """Track in-game time for a campaign."""

    __tablename__ = "campaign_calendars"

    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id"),
        nullable=False,
        unique=True,
    )

    # Current date/time
    current_day = Column(Integer, default=1, nullable=False)
    current_month = Column(Integer, default=1, nullable=False)  # 1-12
    current_year = Column(Integer, default=1, nullable=False)
    current_hour = Column(Integer, default=8, nullable=False)  # 0-23

    # Moon tracking
    moon_day = Column(Integer, default=0, nullable=False)  # Day in moon cycle (0-27)

    # Calendar configuration
    calendar_config = Column(JSONB, default=DEFAULT_CALENDAR_CONFIG)

    # Scheduled events (recurring or one-time)
    scheduled_events = Column(JSONB, default=[])
    # Format: [{"id": uuid, "name": str, "day": int, "month": int, "year": int|null,
    #           "recurring": bool, "triggered": bool, "description": str}]

    # Weather state (updated when time advances)
    current_weather = Column(String(100), nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="calendar")

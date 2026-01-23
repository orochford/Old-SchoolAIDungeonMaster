from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.shared.base_model import BaseModel


class ItemTemplate(Base, BaseModel):
    """Master item definitions per RPG system."""

    __tablename__ = "item_templates"

    rpg_system_id = Column(UUID(as_uuid=True), ForeignKey("rpg_systems.id"), nullable=False)

    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)  # weapon, armor, gear, treasure, etc.

    # Item properties
    weight = Column(Numeric(10, 2), default=0)
    base_value_gp = Column(Integer, default=0)

    # System-specific properties (damage, AC bonus, etc.)
    properties = Column(JSONB, default={})

    # Is this a magical item?
    is_magical = Column(Boolean, default=False)

    # Relationships
    inventory_items = relationship("CharacterInventory", back_populates="item_template")


class CharacterInventory(Base, BaseModel):
    """Items owned by characters."""

    __tablename__ = "character_inventory"

    character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)
    item_template_id = Column(UUID(as_uuid=True), ForeignKey("item_templates.id"), nullable=True)

    # For custom/unique items not in templates
    custom_name = Column(String(100))
    custom_description = Column(Text)
    custom_properties = Column(JSONB, default={})

    quantity = Column(Integer, default=1, nullable=False)
    is_equipped = Column(Boolean, default=False)
    is_identified = Column(Boolean, default=True)

    # Container/location within inventory
    container = Column(String(50))  # backpack, belt, worn, etc.

    # Notes about this specific item
    notes = Column(Text)

    # Relationships
    character = relationship("Character", back_populates="inventory")
    item_template = relationship("ItemTemplate", back_populates="inventory_items")

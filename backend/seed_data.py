"""Seed initial data for the Solo RPG Platform."""

import asyncio
from uuid import uuid4
from sqlalchemy import select
from app.core.database import AsyncSessionLocal

# Import all models to ensure relationships are resolved
from app.domains.campaigns.models import RPGSystem, Campaign
from app.domains.characters.models import Character, CharacterLevelHistory
from app.domains.sessions.models import Session, ConversationMessage
from app.domains.combat.models import CombatEncounter, CombatParticipant, ConditionTemplate, ActiveCondition
from app.domains.npcs.models import NPCDetails, NPCRelationship, DispositionHistory
from app.domains.inventory.models import ItemTemplate, CharacterInventory
from app.domains.sourcebooks.models import PDFDocument, PDFChunk
from app.domains.journal.models import JournalEntry, Achievement, CharacterAchievement, WorldLocation, WorldConsequence, EquipmentHistory


RPG_SYSTEMS = [
    {
        "code": "bx-dnd",
        "name": "Basic/Expert D&D (1981)",
        "description": "The classic Basic/Expert Dungeons & Dragons rules edited by Tom Moldvay (Basic) and David Cook (Expert) in 1981. Features race-as-class, descending AC, THAC0, and old-school dungeon crawling.",
        "version": "1981",
        "config": {
            "uses_thac0": True,
            "descending_ac": True,
            "race_as_class": True,
            "xp_for_gold": True,
            "morale_checks": True,
            "reaction_rolls": True,
            "saving_throw_categories": [
                "Death Ray or Poison",
                "Magic Wands",
                "Paralysis or Turn to Stone",
                "Dragon Breath",
                "Rods, Staves, or Spells"
            ],
            "classes": ["Fighter", "Magic-User", "Cleric", "Thief", "Elf", "Dwarf", "Halfling"],
            "max_level": 14,
            "ability_scores": ["STR", "INT", "WIS", "DEX", "CON", "CHA"],
            "alignment_options": ["Lawful", "Neutral", "Chaotic"]
        }
    },
    {
        "code": "osr-dnd",
        "name": "OSR / Old-School Essentials",
        "description": "Old-School Renaissance games compatible with B/X D&D, including Old-School Essentials, Labyrinth Lord, and other OSR retroclones. Uses THAC0, descending AC, and classic dungeon crawling mechanics.",
        "version": "OSR",
        "config": {
            "uses_thac0": True,
            "descending_ac": True,
            "race_as_class": True,
            "xp_for_gold": True,
            "morale_checks": True,
            "reaction_rolls": True,
            "saving_throw_categories": [
                "Death Ray or Poison",
                "Magic Wands",
                "Paralysis or Turn to Stone",
                "Dragon Breath",
                "Rods, Staves, or Spells"
            ],
            "classes": ["Fighter", "Magic-User", "Cleric", "Thief", "Elf", "Dwarf", "Halfling"],
            "max_level": 14,
            "ability_scores": ["STR", "INT", "WIS", "DEX", "CON", "CHA"],
            "alignment_options": ["Lawful", "Neutral", "Chaotic"]
        }
    },
]


async def seed_rpg_systems():
    """Seed all RPG systems."""
    async with AsyncSessionLocal() as db:
        created = []
        for system_data in RPG_SYSTEMS:
            # Check if already exists
            result = await db.execute(
                select(RPGSystem).where(RPGSystem.code == system_data["code"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"  {system_data['name']} already exists (ID: {existing.id})")
                if system_data["code"] == "bx-dnd":
                    created.append(existing.id)
                continue

            # Create system
            system = RPGSystem(
                id=uuid4(),
                name=system_data["name"],
                code=system_data["code"],
                description=system_data["description"],
                version=system_data.get("version"),
                config=system_data.get("config", {}),
            )

            db.add(system)
            await db.flush()
            print(f"  Created {system_data['name']} (ID: {system.id})")
            if system_data["code"] == "bx-dnd":
                created.append(system.id)

        await db.commit()
        return created[0] if created else None


async def main():
    """Run all seed functions."""
    print("Seeding database...")
    system_id = await seed_rpg_systems()
    print(f"\nSeeding complete!")
    print(f"B/X D&D System ID: {system_id}")
    print("\nYou can now:")
    print("1. Start the backend: uvicorn app.main:app --reload")
    print("2. Start the frontend: cd ../frontend && npm run dev")
    print("3. Access the app at http://localhost:5173")


if __name__ == "__main__":
    asyncio.run(main())

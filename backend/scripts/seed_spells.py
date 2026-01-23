#!/usr/bin/env python3
"""Seed spell data from OSE reference."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from uuid import uuid4
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.domains.spells.models import Spell
from app.domains.spells.spell_data import ALL_SPELLS


async def seed_spells():
    """Seed all spells into the database."""
    async with AsyncSessionLocal() as db:
        # Check if spells already exist
        result = await db.execute(select(Spell).limit(1))
        existing = result.scalar_one_or_none()

        if existing:
            print("Spells already seeded. Skipping...")
            return

        print(f"Seeding {len(ALL_SPELLS)} spells...")

        for spell_data in ALL_SPELLS:
            spell = Spell(
                id=uuid4(),
                name=spell_data["name"],
                code=spell_data["code"],
                level=spell_data["level"],
                spell_class=spell_data["spell_class"],
                duration=spell_data.get("duration"),
                range=spell_data.get("range"),
                description=spell_data["description"],
                reversible=spell_data.get("reversible", False),
                reversed_name=spell_data.get("reversed_name"),
                save=spell_data.get("save"),
                area_of_effect=spell_data.get("area_of_effect"),
                source_book="OSE Basic",
            )
            db.add(spell)

        await db.commit()
        print("Spells seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed_spells())

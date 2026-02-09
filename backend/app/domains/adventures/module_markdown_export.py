"""Export structured module data from DB as well-organized markdown for LLM reference."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.adventures.models import (
    AdventureModule,
    AdventureLocation,
    AdventureNPC,
    AdventureEncounter,
    AdventureItem,
    AdventureStoryBeat,
    EncounterType,
)

logger = logging.getLogger(__name__)


async def export_module_markdown(db: AsyncSession, module_id: UUID) -> str:
    """Query all extracted DB data for a module and return formatted markdown.

    This produces a structured, enriched markdown document from the multi-pass
    extraction results — not the raw OCR text. Designed for easy LLM consumption.
    """
    # Load module
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise ValueError(f"Module {module_id} not found")

    # Load all related data
    result = await db.execute(
        select(AdventureLocation)
        .where(AdventureLocation.module_id == module_id)
        .order_by(AdventureLocation.location_key)
    )
    locations = list(result.scalars().all())

    result = await db.execute(
        select(AdventureNPC)
        .where(AdventureNPC.module_id == module_id)
        .order_by(AdventureNPC.name)
    )
    npcs = list(result.scalars().all())

    result = await db.execute(
        select(AdventureEncounter)
        .where(AdventureEncounter.module_id == module_id)
        .order_by(AdventureEncounter.name)
    )
    encounters = list(result.scalars().all())

    result = await db.execute(
        select(AdventureItem)
        .where(AdventureItem.module_id == module_id)
        .order_by(AdventureItem.name)
    )
    items = list(result.scalars().all())

    result = await db.execute(
        select(AdventureStoryBeat)
        .where(AdventureStoryBeat.module_id == module_id)
        .order_by(AdventureStoryBeat.sequence)
    )
    story_beats = list(result.scalars().all())

    # Build location lookup by id for NPC/encounter location references
    location_by_id = {loc.id: loc for loc in locations}

    # Build markdown
    parts = []

    # --- Header ---
    title_line = f"# {module.title}"
    if module.code:
        title_line += f" ({module.code})"
    parts.append(title_line)

    meta_parts = []
    if module.recommended_level_min or module.recommended_level_max:
        lvl_min = module.recommended_level_min or "?"
        lvl_max = module.recommended_level_max or "?"
        meta_parts.append(f"Levels: {lvl_min}-{lvl_max}")
    if module.recommended_party_size_min or module.recommended_party_size_max:
        ps_min = module.recommended_party_size_min or "?"
        ps_max = module.recommended_party_size_max or "?"
        meta_parts.append(f"Party Size: {ps_min}-{ps_max}")
    if meta_parts:
        parts.append(" | ".join(meta_parts))
    parts.append("")

    # --- Summary ---
    if module.summary:
        parts.append("## Summary")
        parts.append(module.summary)
        parts.append("")

    # --- Player Background ---
    if module.player_background:
        parts.append("## Player Background")
        parts.append(module.player_background)
        parts.append("")

    # --- Adventure Flow ---
    if module.adventure_flow:
        parts.append("## Adventure Flow")
        parts.append(module.adventure_flow)
        parts.append("")

    # --- DM Overview ---
    if module.dm_overview:
        parts.append("## DM Overview")
        parts.append(module.dm_overview)
        parts.append("")

    # --- Maps & Illustrations ---
    maps = module.maps or []
    illustrations = module.illustrations or []
    if maps or illustrations:
        parts.append("## Maps & Illustrations")
        if maps:
            parts.append("### Maps")
            for m in maps:
                if isinstance(m, dict):
                    title = m.get("title", "Untitled Map")
                    page = m.get("page")
                    page_str = f" (page {page})" if page else ""
                    parts.append(f"- {title}{page_str}")
        if illustrations:
            parts.append("### Illustrations")
            for ill in illustrations:
                if isinstance(ill, dict):
                    title = ill.get("title", "Untitled")
                    page = ill.get("page")
                    page_str = f" (page {page})" if page else ""
                    parts.append(f"- {title}{page_str}")
        parts.append("")

    # --- Rumors ---
    rumors = module.rumors_table or []
    if rumors:
        parts.append("## Rumors")
        parts.append("| Roll | Rumor | True? |")
        parts.append("|------|-------|-------|")
        for r in rumors:
            roll = r.get("roll", "?")
            rumor = r.get("rumor", "")
            is_true = r.get("is_true")
            true_str = "Yes" if is_true is True else ("No" if is_true is False else "?")
            # Escape pipes in rumor text
            rumor = rumor.replace("|", "\\|")
            parts.append(f"| {roll} | {rumor} | {true_str} |")
        parts.append("")

    # --- Locations ---
    if locations:
        parts.append(f"## Locations ({len(locations)})")
        parts.append("")

        for loc in locations:
            parts.append(f"### {loc.location_key}. {loc.name}")

            loc_meta = []
            if loc.dungeon_level:
                loc_meta.append(f"**Level**: {loc.dungeon_level}")
            if loc.tier:
                loc_meta.append(f"**Tier**: {loc.tier}")
            if loc.map_image_id:
                # Find map title from module maps metadata
                map_title = None
                for m in (module.maps or []):
                    if isinstance(m, dict) and str(m.get("image_id", "")) == str(loc.map_image_id):
                        map_title = m.get("title")
                        break
                loc_meta.append(f"**Map**: {map_title or 'Yes'}")
            if loc.exits and isinstance(loc.exits, dict) and loc.exits:
                exits_formatted = ", ".join(
                    f"{direction} → {dest}" for direction, dest in loc.exits.items()
                )
                loc_meta.append(f"**Exits**: {exits_formatted}")
            if loc_meta:
                parts.append(" | ".join(loc_meta))
            parts.append("")

            if loc.read_aloud_text:
                parts.append(f"> {loc.read_aloud_text}")
                parts.append("")

            if loc.dm_description:
                parts.append(loc.dm_description)
                parts.append("")

            if loc.features:
                feature_strs = []
                for f in loc.features:
                    if isinstance(f, dict):
                        name = f.get("feature", f.get("name", ""))
                        details = f.get("details", "")
                        feature_strs.append(f"{name}: {details}" if details else name)
                    else:
                        feature_strs.append(str(f))
                if feature_strs:
                    parts.append(f"**Features**: {'; '.join(feature_strs)}")
                    parts.append("")

            if loc.traps:
                for trap in loc.traps:
                    if isinstance(trap, dict):
                        trigger = trap.get("trigger", "?")
                        effect = trap.get("effect", "?")
                        detection = trap.get("detection", "")
                        disarm = trap.get("disarm", "")
                        trap_str = f"**Trap**: {trigger} — {effect}"
                        if detection:
                            trap_str += f" (Detect: {detection})"
                        if disarm:
                            trap_str += f" (Disarm: {disarm})"
                        parts.append(trap_str)
                    else:
                        parts.append(f"**Trap**: {trap}")
                parts.append("")

            if loc.secrets:
                for secret in loc.secrets:
                    if isinstance(secret, dict):
                        stype = secret.get("type", "secret")
                        detection = secret.get("detection", "")
                        desc = secret.get("description", "")
                        secret_str = f"**Secret ({stype})**: {desc}"
                        if detection:
                            secret_str += f" (Detection: {detection})"
                        parts.append(secret_str)
                    else:
                        parts.append(f"**Secret**: {secret}")
                parts.append("")

            if loc.treasure:
                treasure_strs = []
                for t in loc.treasure:
                    if isinstance(t, dict):
                        item = t.get("item", "?")
                        value = t.get("value", "")
                        location = t.get("location", "")
                        t_str = item
                        if value:
                            t_str += f" ({value})"
                        if location:
                            t_str += f" — {location}"
                        treasure_strs.append(t_str)
                    else:
                        treasure_strs.append(str(t))
                if treasure_strs:
                    parts.append(f"**Treasure**: {'; '.join(treasure_strs)}")
                    parts.append("")

            if loc.atmosphere or loc.sensory_details:
                atmo_parts = []
                if loc.atmosphere:
                    atmo_parts.append(loc.atmosphere)
                if loc.sensory_details and isinstance(loc.sensory_details, dict):
                    for sense, detail in loc.sensory_details.items():
                        if detail:
                            atmo_parts.append(f"{sense}: {detail}")
                if atmo_parts:
                    parts.append(f"**Atmosphere**: {'; '.join(atmo_parts)}")
                    parts.append("")

            if loc.dm_guidance:
                parts.append(f"**DM Guidance**: {loc.dm_guidance}")
                parts.append("")

    # --- NPCs ---
    if npcs:
        parts.append(f"## NPCs ({len(npcs)})")
        parts.append("")

        for npc in npcs:
            header = f"### {npc.name}"
            if npc.title:
                header += f" — {npc.title}"
            parts.append(header)

            npc_meta = []
            if npc.location_id and npc.location_id in location_by_id:
                loc = location_by_id[npc.location_id]
                npc_meta.append(f"**Location**: {loc.location_key}. {loc.name}")
            if npc.initial_disposition and npc.initial_disposition != "neutral":
                npc_meta.append(f"**Disposition**: {npc.initial_disposition}")
            if npc.faction:
                npc_meta.append(f"**Faction**: {npc.faction}")
            if npc_meta:
                parts.append(" | ".join(npc_meta))

            # Stats
            stats = npc.stats or {}
            if stats:
                stat_parts = []
                for key in ["hd", "hp", "ac", "thac0", "save", "morale"]:
                    if key in stats:
                        stat_parts.append(f"{key.upper()} {stats[key]}")
                if stat_parts:
                    parts.append(f"**Stats**: {', '.join(stat_parts)}")
                if stats.get("attacks"):
                    attacks = stats["attacks"]
                    if isinstance(attacks, list):
                        parts.append(f"**Attacks**: {', '.join(str(a) for a in attacks)}")
                if stats.get("damage"):
                    damage = stats["damage"]
                    if isinstance(damage, list):
                        parts.append(f"**Damage**: {', '.join(str(d) for d in damage)}")

            if npc.description:
                parts.append(npc.description)
            if npc.appearance:
                parts.append(f"**Appearance**: {npc.appearance}")

            if npc.personality:
                parts.append(f"**Personality**: {npc.personality}")
            if npc.motivation:
                parts.append(f"**Motivation**: {npc.motivation}")

            if npc.equipment:
                eq_list = npc.equipment
                if isinstance(eq_list, list):
                    parts.append(f"**Equipment**: {', '.join(str(e) for e in eq_list)}")

            if npc.spells:
                spell_list = npc.spells
                if isinstance(spell_list, list):
                    parts.append(f"**Spells**: {', '.join(str(s) for s in spell_list)}")

            if npc.dialogue_hooks:
                hooks = npc.dialogue_hooks
                if isinstance(hooks, list) and hooks:
                    parts.append("**Dialogue Hooks**:")
                    for hook in hooks:
                        if isinstance(hook, dict):
                            topic = hook.get("topic", "")
                            response = hook.get("response", "")
                            condition = hook.get("condition", "")
                            hook_str = f"- *{topic}*: {response}"
                            if condition:
                                hook_str += f" (if: {condition})"
                            parts.append(hook_str)
                        else:
                            parts.append(f"- {hook}")

            parts.append("")

    # --- Encounters ---
    fixed_encounters = [e for e in encounters if e.encounter_type == EncounterType.FIXED]
    wandering_encounters = [e for e in encounters if e.encounter_type == EncounterType.WANDERING]

    if encounters:
        parts.append("## Encounters")
        parts.append("")

    if fixed_encounters:
        parts.append("### Fixed Encounters")
        parts.append("")

        for enc in fixed_encounters:
            # Header with location if available
            header = f"**{enc.name}**"
            if enc.location_id and enc.location_id in location_by_id:
                loc = location_by_id[enc.location_id]
                header = f"**{loc.location_key}. {enc.name}**"
            parts.append(header)

            if enc.description:
                parts.append(enc.description)

            # Creatures
            if enc.creatures:
                for creature in enc.creatures:
                    if isinstance(creature, dict):
                        c_name = creature.get("name", "?")
                        c_count = creature.get("count", 1)
                        c_hd = creature.get("hd", "?")
                        c_hp = creature.get("hp", "?")
                        c_ac = creature.get("ac", "?")
                        c_thac0 = creature.get("thac0", "?")
                        c_morale = creature.get("morale", "?")
                        c_attacks = creature.get("attacks", [])
                        c_damage = creature.get("damage", [])
                        atk_str = ", ".join(str(a) for a in c_attacks) if isinstance(c_attacks, list) else str(c_attacks)
                        dmg_str = ", ".join(str(d) for d in c_damage) if isinstance(c_damage, list) else str(c_damage)
                        parts.append(
                            f"- {c_name} (×{c_count}): HD {c_hd}, HP {c_hp}, AC {c_ac}, "
                            f"THAC0 {c_thac0}, Morale {c_morale}, Atk: {atk_str}, Dmg: {dmg_str}"
                        )

            if enc.tactics:
                parts.append(f"**Tactics**: {enc.tactics}")

            if enc.treasure:
                treasure_strs = []
                for t in enc.treasure:
                    if isinstance(t, dict):
                        treasure_strs.append(t.get("item", str(t)))
                    else:
                        treasure_strs.append(str(t))
                if treasure_strs:
                    parts.append(f"**Treasure**: {', '.join(treasure_strs)}")

            if enc.trigger_condition:
                parts.append(f"**Trigger**: {enc.trigger_condition}")

            if enc.xp_value:
                parts.append(f"**XP**: {enc.xp_value}")

            parts.append("")

    if wandering_encounters:
        parts.append("### Wandering Monsters")
        parts.append("")

        # Group by table name
        tables: dict[str, list] = {}
        for enc in wandering_encounters:
            table_name = enc.wandering_table_name or "Default"
            tables.setdefault(table_name, []).append(enc)

        for table_name, entries in tables.items():
            # Get die_roll and frequency from first entry
            first = entries[0]
            die_roll = first.die_roll or "1d6"
            frequency = first.check_frequency or ""

            header = f"**{table_name}**"
            if frequency:
                header += f" (Check: {frequency}, Roll: {die_roll})"
            else:
                header += f" (Roll: {die_roll})"
            parts.append(header)

            parts.append("| Roll | Encounter |")
            parts.append("|------|-----------|")
            for enc in sorted(entries, key=lambda e: e.roll_range or ""):
                roll_range = enc.roll_range or "?"
                # Build creature summary
                creature_strs = []
                for c in (enc.creatures or []):
                    if isinstance(c, dict):
                        c_name = c.get("name", "?")
                        c_count = c.get("count", 1)
                        creature_strs.append(f"{c_name} (×{c_count})")
                    else:
                        creature_strs.append(str(c))
                creature_summary = ", ".join(creature_strs) if creature_strs else enc.name
                # Escape pipes
                creature_summary = creature_summary.replace("|", "\\|")
                parts.append(f"| {roll_range} | {creature_summary} |")
            parts.append("")

    # --- Key Items ---
    if items:
        parts.append(f"## Key Items ({len(items)})")
        parts.append("")

        for item in items:
            item_str = f"- **{item.name}**"
            if item.item_type:
                item_str += f" ({item.item_type})"
            item_str += ":"
            if item.description:
                item_str += f" {item.description}"
            if item.magical_properties:
                item_str += f" — *{item.magical_properties}*"
            if item.value:
                item_str += f" — Value: {item.value}"
            if item.found_at:
                item_str += f" — Found: {item.found_at}"
            elif item.location_id and item.location_id in location_by_id:
                loc = location_by_id[item.location_id]
                item_str += f" — Found: {loc.location_key}. {loc.name}"
            parts.append(item_str)
        parts.append("")

    # --- Story Progression ---
    if story_beats:
        parts.append("## Story Progression")
        parts.append("")

        for beat in story_beats:
            prefix = f"{beat.sequence}. **{beat.name}**"
            if beat.is_critical_path:
                prefix += " ★"
            parts.append(prefix)
            if beat.description:
                parts.append(f"   {beat.description}")
            if beat.trigger and isinstance(beat.trigger, dict):
                t_type = beat.trigger.get("type", "")
                t_value = beat.trigger.get("value", "")
                if t_type and t_value:
                    parts.append(f"   *Trigger*: {t_type} — {t_value}")
            if beat.related_locations:
                parts.append(f"   *Locations*: {', '.join(beat.related_locations)}")
            if beat.branches and isinstance(beat.branches, list):
                for branch in beat.branches:
                    if isinstance(branch, dict):
                        condition = branch.get("condition", "")
                        consequence = branch.get("consequence", "")
                        if condition or consequence:
                            parts.append(f"   - If {condition}: {consequence}")
            parts.append("")

    # --- Critical Path ---
    if module.critical_path:
        critical_path = module.critical_path
        if isinstance(critical_path, list) and critical_path:
            parts.append("## Critical Path")
            parts.append(" → ".join(str(k) for k in critical_path))
            parts.append("")

    return "\n".join(parts)

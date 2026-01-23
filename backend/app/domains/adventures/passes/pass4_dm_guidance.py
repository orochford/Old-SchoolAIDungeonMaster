"""Pass 4: DM Guidance extraction.

This pass extracts how-to-run information:
- How to run each area
- Secrets and reveals
- Common player actions and responses
- Difficulty scaling notes
"""

import logging
from typing import Dict, Any, List

from sqlalchemy import select, update

from app.domains.adventures.models import AdventureModule, AdventureLocation
from app.domains.adventures.extraction_context import (
    ExtractionContext, DMGuidance, Secret
)
from app.domains.adventures.passes.base import BasePass

logger = logging.getLogger(__name__)


PASS4_DM_GUIDANCE_PROMPT = """You are extracting DM guidance from a tabletop RPG adventure module.

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Based on what you know about the adventure, extract guidance for running it:

### PER-LOCATION GUIDANCE
For key locations (especially puzzle rooms, boss areas, complex areas):
- how_to_run: How should the DM run this area?
- common_mistakes: What do DMs/players commonly get wrong?
- player_actions: Common player actions and how to respond
- scaling: How to adjust difficulty up/down
- secrets_to_reveal: Information to reveal through play
- foreshadowing: What hints to drop about other areas

### MODULE-WIDE GUIDANCE
- pacing: How to pace the adventure
- difficulty: Overall difficulty notes
- foreshadowing: Key plot points to hint at
- common_mistakes: Pitfalls for new DMs

### SECRETS & REVEALS
Major secrets in the adventure:
- name: Secret name
- description: What the secret is
- location_keys: Which locations relate to this secret
- reveal_conditions: When/how players learn this
- player_impact: How knowing this affects gameplay

## OUTPUT FORMAT
```json
{{
  "per_location": {{
    "31": {{
      "how_to_run": "This is a puzzle room. Let players experiment with the pools...",
      "common_mistakes": "Players often drink from pools without testing",
      "player_actions": [{{"action": "Drink from pool", "response": "Roll on pool effects table"}}],
      "scaling": "For weaker parties, reduce poison damage",
      "secrets_to_reveal": ["Pool 3 grants wishes but has a dark cost"],
      "foreshadowing": "Mention strange glowing light from this direction earlier"
    }}
  }},
  "module_wide": {{
    "pacing": "Upper level should take 1-2 sessions, lower level 2-3",
    "difficulty": "Challenging for levels 1-3, add monsters for higher levels",
    "foreshadowing": ["Mention Rogahn/Zelligar names early", "Describe ancient battles"],
    "common_mistakes": ["Letting players rest too often", "Missing the secret level"]
  }},
  "secrets": [
    {{
      "name": "Rogahn's Hidden Treasury",
      "description": "A secret vault containing Rogahn's most valuable possessions",
      "location_keys": ["45", "46"],
      "reveal_conditions": "Finding the secret door in room 45",
      "player_impact": "Major treasure reward, possible magic items"
    }}
  ]
}}
```

## TEXT TO ANALYZE
{text}
"""


class DMGuidancePass(BasePass):
    """Pass 4: Extract DM guidance and secrets."""

    name = "pass4_dm_guidance"
    description = "Extract DM guidance and secrets"

    async def execute(
        self,
        module: AdventureModule,
        full_text: str,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
    ) -> ExtractionContext:
        """Extract DM guidance.

        Input: Full context so far
        Output: Per-location DM notes, module secrets
        """
        self._log("Extracting DM guidance...")
        updates = ExtractionContext()

        # Build comprehensive context
        context_prompt = context.to_context_prompt([
            'overview', 'locations_summary', 'encounters', 'npcs'
        ])

        # Call LLM
        prompt = PASS4_DM_GUIDANCE_PROMPT.replace("{context}", context_prompt)
        result = await self._call_llm(prompt, full_text, stage_name="pass4_dm_guidance")

        if not result:
            self._log("WARNING: No DM guidance extracted")
            return updates

        # Process per-location guidance
        per_location = result.get('per_location', {})
        self._log(f"Found guidance for {len(per_location)} locations")

        for location_key, guidance_data in per_location.items():
            guidance = DMGuidance(
                location_key=location_key,
                how_to_run=guidance_data.get('how_to_run', ''),
                common_mistakes=guidance_data.get('common_mistakes'),
                player_actions=guidance_data.get('player_actions', []),
                scaling_notes=guidance_data.get('scaling'),
                secrets_to_reveal=guidance_data.get('secrets_to_reveal', []),
                foreshadowing=guidance_data.get('foreshadowing'),
            )
            updates.dm_notes[location_key] = guidance

            # Update database record
            await self._update_location_guidance(module, location_key, guidance_data)

        # Process module-wide guidance
        module_wide = result.get('module_wide', {})
        if module_wide:
            parts = []
            if module_wide.get('pacing'):
                parts.append(f"Pacing: {module_wide['pacing']}")
            if module_wide.get('difficulty'):
                parts.append(f"Difficulty: {module_wide['difficulty']}")
            if module_wide.get('foreshadowing'):
                hints = module_wide['foreshadowing']
                if isinstance(hints, list):
                    parts.append(f"Foreshadowing: {'; '.join(hints)}")
                else:
                    parts.append(f"Foreshadowing: {hints}")
            if module_wide.get('common_mistakes'):
                mistakes = module_wide['common_mistakes']
                if isinstance(mistakes, list):
                    parts.append(f"Avoid: {'; '.join(mistakes)}")
                else:
                    parts.append(f"Avoid: {mistakes}")

            updates.module_dm_guidance = "\n".join(parts)

            # Update module record
            if hasattr(module, 'dm_overview'):
                module.dm_overview = updates.module_dm_guidance
                await self.db.flush()

        # Process secrets
        secrets_data = result.get('secrets', [])
        self._log(f"Found {len(secrets_data)} module secrets")

        for secret_data in secrets_data:
            secret = Secret(
                name=secret_data.get('name', 'Unknown Secret'),
                description=secret_data.get('description', ''),
                location_keys=secret_data.get('location_keys', []),
                reveal_conditions=secret_data.get('reveal_conditions'),
                player_impact=secret_data.get('player_impact'),
            )
            updates.secrets.append(secret)

        self._log(f"Extracted guidance for {len(updates.dm_notes)} locations")
        self._log(f"Extracted {len(updates.secrets)} secrets")

        return updates

    async def _update_location_guidance(
        self,
        module: AdventureModule,
        location_key: str,
        guidance_data: Dict[str, Any],
    ) -> None:
        """Update location record with DM guidance."""
        # Find the location
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module.id)
            .where(AdventureLocation.location_key == str(location_key))
        )
        location = result.scalar_one_or_none()

        if not location:
            return

        # Build guidance text
        parts = []
        if guidance_data.get('how_to_run'):
            parts.append(guidance_data['how_to_run'])
        if guidance_data.get('common_mistakes'):
            parts.append(f"Common mistakes: {guidance_data['common_mistakes']}")
        if guidance_data.get('scaling'):
            parts.append(f"Scaling: {guidance_data['scaling']}")

        guidance_text = "\n\n".join(parts)

        # Update if location has dm_guidance field
        if hasattr(location, 'dm_guidance'):
            location.dm_guidance = guidance_text
            await self.db.flush()

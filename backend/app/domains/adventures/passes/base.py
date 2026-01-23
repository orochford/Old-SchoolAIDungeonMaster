"""Base class for extraction passes."""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.adventures.models import AdventureModule
from app.domains.adventures.extraction_context import ExtractionContext

logger = logging.getLogger(__name__)


class BasePass(ABC):
    """Base class for multi-pass extraction passes.

    Each pass:
    1. Receives current context from previous passes
    2. Extracts specific information from the adventure text
    3. Returns updates to merge into the context
    """

    name: str = "base"
    description: str = "Base pass"

    def __init__(self, db: AsyncSession):
        self.db = db
        self._log_messages: List[str] = []

    def _log(self, message: str) -> None:
        """Add a log message."""
        logger.info(f"[{self.name}] {message}")
        self._log_messages.append(message)

    def get_log_messages(self) -> List[str]:
        """Get accumulated log messages."""
        return list(self._log_messages)

    def clear_log_messages(self) -> None:
        """Clear accumulated log messages."""
        self._log_messages = []

    @abstractmethod
    async def execute(
        self,
        module: AdventureModule,
        full_text: str,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
    ) -> ExtractionContext:
        """Execute the pass and return context updates.

        Args:
            module: The AdventureModule being parsed
            full_text: Full text of the adventure document
            preprocessed: Results from preprocessing (sections, rooms, wandering tables)
            context: Current extraction context from previous passes

        Returns:
            ExtractionContext with updates from this pass (will be merged)
        """
        pass

    async def _call_llm(
        self,
        prompt: str,
        text: str,
        max_retries: int = 2,
        stage_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call the LLM and parse JSON response.

        Uses the configured processing AI provider.
        """
        import anthropic
        import openai
        from app.config import settings

        stage = stage_name or self.name
        clean_text = self._sanitize_text(text[:100000])

        # Format prompt with text
        if "{text}" in prompt:
            formatted_prompt = prompt.format(text=clean_text)
        else:
            formatted_prompt = prompt + f"\n\nText to analyze:\n{clean_text}"

        system_prompt = (
            "You are a precise data extractor for tabletop RPG adventure modules. "
            "CRITICAL: Always respond with valid JSON only. "
            "Your response must start with { and end with }. "
            "No markdown code blocks, no explanation text, just the JSON object."
        )

        logger.info(f"[{stage}] Starting LLM call (text length: {len(clean_text)} chars)")
        logger.info(f"[{stage}] Provider: {settings.processing_provider}")

        if settings.processing_provider == "openai":
            result = await self._call_openai(
                formatted_prompt, system_prompt, max_retries, stage, settings
            )
        else:
            result = await self._call_claude(
                formatted_prompt, system_prompt, max_retries, stage
            )

        if result is not None:
            return result

        logger.error(f"[{stage}] LLM call failed")
        return {}

    async def _call_claude(
        self,
        formatted_prompt: str,
        system_prompt: str,
        max_retries: int,
        stage_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Call Claude API with retries."""
        import anthropic
        from app.config import settings

        model = settings.processing_claude_model or "claude-haiku-4-5-20250101"
        self._log(f"Using Claude ({model})...")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"[{stage_name}] Attempt {attempt + 1}/{max_retries + 1}")

                client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
                response = await client.messages.create(
                    model=model,
                    messages=[{"role": "user", "content": formatted_prompt}],
                    system=system_prompt,
                    max_tokens=8192,
                )

                content = ""
                if response.content:
                    for block in response.content:
                        if hasattr(block, 'text'):
                            content = block.text
                            break

                if not content:
                    logger.warning(f"[{stage_name}] Empty response from Claude")
                    continue

                parsed = self._extract_json(content, stage_name)
                if parsed is not None:
                    logger.info(f"[{stage_name}] Successfully parsed JSON")
                    return parsed

            except anthropic.AuthenticationError as e:
                self._log("ERROR: Claude API authentication failed")
                logger.error(f"[{stage_name}] Claude auth error: {e}")
                return None
            except anthropic.RateLimitError as e:
                self._log("ERROR: Claude API rate limit exceeded")
                logger.error(f"[{stage_name}] Claude rate limit: {e}")
                return None
            except anthropic.APIStatusError as e:
                if "credit" in str(e).lower() or "billing" in str(e).lower():
                    self._log("ERROR: Claude API credits exhausted")
                    return None
                last_error = e
                logger.warning(f"[{stage_name}] Claude API error (attempt {attempt + 1}): {e}")
            except Exception as e:
                last_error = e
                logger.warning(f"[{stage_name}] Claude call failed (attempt {attempt + 1}): {e}")

        if last_error:
            logger.error(f"[{stage_name}] All attempts failed. Last error: {last_error}")
        return None

    async def _call_openai(
        self,
        formatted_prompt: str,
        system_prompt: str,
        max_retries: int,
        stage_name: str,
        settings,
    ) -> Optional[Dict[str, Any]]:
        """Call OpenAI API with retries."""
        import openai

        if not settings.openai_api_key:
            self._log("ERROR: No OpenAI API key configured")
            return None

        model = settings.processing_openai_model or "gpt-4o-mini"
        self._log(f"Using OpenAI ({model})...")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"[{stage_name}] Attempt {attempt + 1}/{max_retries + 1}")

                client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": formatted_prompt}
                    ],
                )

                content = response.choices[0].message.content
                if not content:
                    logger.warning(f"[{stage_name}] Empty response from OpenAI")
                    continue

                parsed = self._extract_json(content, stage_name)
                if parsed is not None:
                    logger.info(f"[{stage_name}] Successfully parsed JSON")
                    return parsed

            except Exception as e:
                last_error = e
                logger.warning(f"[{stage_name}] OpenAI call failed (attempt {attempt + 1}): {e}")

        if last_error:
            self._log(f"ERROR: OpenAI failed: {str(last_error)[:100]}")
            logger.error(f"[{stage_name}] All attempts failed. Last error: {last_error}")
        return None

    def _sanitize_text(self, text: str) -> str:
        """Sanitize text for LLM processing."""
        # Remove null bytes and problematic characters
        text = text.replace('\x00', '')
        # Replace multiple whitespace with single space (keep newlines)
        text = re.sub(r'[^\S\n]+', ' ', text)
        # Remove very long sequences of repeated characters
        text = re.sub(r'(.)\1{20,}', r'\1\1\1', text)
        return text

    def _extract_json(self, content: str, stage_name: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM response."""
        content = content.strip()

        # Remove markdown code blocks
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Find JSON object with balanced braces
        brace_start = content.find('{')
        if brace_start != -1:
            depth = 0
            brace_end = -1
            for i, c in enumerate(content[brace_start:], start=brace_start):
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        brace_end = i
                        break

            if brace_end != -1:
                json_str = content[brace_start:brace_end + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Try fixing common issues
                    fixed = self._fix_json(json_str)
                    try:
                        return json.loads(fixed)
                    except json.JSONDecodeError:
                        pass

        # Regex fallback
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                fixed = self._fix_json(json_match.group(0))
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError as e:
                    logger.warning(f"[{stage_name}] All JSON extraction failed: {e}")

        return None

    def _fix_json(self, content: str) -> str:
        """Attempt to fix common JSON formatting issues."""
        # Remove trailing commas before } or ]
        content = re.sub(r',(\s*[}\]])', r'\1', content)
        # Fix unquoted keys
        content = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', content)
        # Remove control characters except newlines/tabs
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)
        return content

    def _safe_int(self, value: Any, default: Optional[int] = None) -> Optional[int]:
        """Safely convert a value to int."""
        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            match = re.search(r'^-?\d+', str(value).strip())
            if match:
                return int(match.group())
        return default

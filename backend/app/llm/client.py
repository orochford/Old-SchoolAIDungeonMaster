"""LLM API client with streaming support for GM (Game Master) interactions."""

from typing import AsyncGenerator, List, Dict, Any, Optional
import logging
import anthropic
from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Async LLM client for GM with streaming and tool support.

    Uses the configured GM provider (Claude or OpenAI) based on settings.
    Settings are read dynamically on each call to support runtime updates.
    """

    def __init__(self):
        # Clients are initialized lazily when needed
        self._claude_client = None
        self._openai_client = None
        # Track API keys to detect changes
        self._claude_api_key = None
        self._openai_api_key = None

    def _get_provider(self) -> str:
        """Get current provider from settings (reads dynamically)."""
        return settings.gm_provider

    def _get_model(self) -> str:
        """Get current model from settings based on provider."""
        if self._get_provider() == "claude":
            return settings.gm_claude_model
        else:
            return settings.gm_openai_model

    def _get_claude_client(self) -> AsyncAnthropic:
        """Get or create Claude client, recreating if API key changed."""
        current_key = settings.anthropic_api_key
        if self._claude_client is None or self._claude_api_key != current_key:
            self._claude_client = AsyncAnthropic(api_key=current_key)
            self._claude_api_key = current_key
            logger.info("Created new Claude client for GM")
        return self._claude_client

    def _get_openai_client(self):
        """Get or create OpenAI client, recreating if API key changed."""
        current_key = settings.openai_api_key
        if self._openai_client is None or self._openai_api_key != current_key:
            import openai
            self._openai_client = openai.AsyncOpenAI(api_key=current_key)
            self._openai_api_key = current_key
            logger.info("Created new OpenAI client for GM")
        return self._openai_client

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Send a chat request and get a complete response."""
        provider = self._get_provider()
        model = self._get_model()
        logger.info(f"GM chat using provider={provider}, model={model}")

        if provider == "openai":
            return await self._chat_openai(messages, system, tools, max_tokens, temperature)

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        client = self._get_claude_client()
        response = await client.messages.create(**kwargs)

        return self._parse_response(response)

    async def _chat_openai(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Send a chat request to OpenAI and get a complete response."""
        model = self._get_model()
        openai_messages = []

        if system:
            openai_messages.append({"role": "system", "content": system})

        # Convert messages to OpenAI format
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Handle complex content (tool results, etc.)
                text_parts = []
                for block in content:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        text_parts.append(f"Tool result: {block.get('content', '')}")
                content = "\n".join(text_parts) if text_parts else str(content)
            openai_messages.append({"role": role, "content": content})

        kwargs = {
            "model": model,
            "max_completion_tokens": max_tokens,  # OpenAI uses max_completion_tokens for newer models
            "messages": openai_messages,
            # Note: Newer OpenAI models (gpt-4.1-mini, etc.) only support temperature=1
            # Omit temperature parameter to use model default
        }

        # Convert Anthropic-style tools to OpenAI function format
        if tools:
            openai_tools = []
            for tool in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    }
                })
            kwargs["tools"] = openai_tools

        client = self._get_openai_client()
        response = await client.chat.completions.create(**kwargs)

        return self._parse_openai_response(response)

    def _parse_openai_response(self, response) -> Dict[str, Any]:
        """Parse an OpenAI API response to match Claude format."""
        choice = response.choices[0]
        result = {
            "id": response.id,
            "model": response.model,
            "stop_reason": "end_turn" if choice.finish_reason == "stop" else choice.finish_reason,
            "content": [],
            "usage": {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }

        if choice.message.content:
            result["content"].append({
                "type": "text",
                "text": choice.message.content,
            })

        if choice.message.tool_calls:
            import json
            for tool_call in choice.message.tool_calls:
                result["content"].append({
                    "type": "tool_use",
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "input": json.loads(tool_call.function.arguments) if tool_call.function.arguments else {},
                })

        return result

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream a chat response."""
        provider = self._get_provider()
        model = self._get_model()
        logger.info(f"GM chat_stream using provider={provider}, model={model}")

        if provider == "openai":
            async for event in self._chat_stream_openai(messages, system, tools, max_tokens, temperature):
                yield event
            return

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        import json

        client = self._get_claude_client()
        async with client.messages.stream(**kwargs) as stream:
            current_text = ""
            current_tool_use = None
            tool_input_json = ""

            async for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "text":
                        current_text = ""
                    elif event.content_block.type == "tool_use":
                        current_tool_use = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input": {},
                        }
                        tool_input_json = ""

                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        current_text += event.delta.text
                        yield {
                            "type": "text_delta",
                            "text": event.delta.text,
                        }
                    elif hasattr(event.delta, "partial_json"):
                        if current_tool_use:
                            tool_input_json += event.delta.partial_json
                            yield {
                                "type": "tool_use_delta",
                                "partial_json": event.delta.partial_json,
                            }

                elif event.type == "content_block_stop":
                    if current_tool_use:
                        # Parse accumulated JSON for tool input
                        if tool_input_json:
                            try:
                                current_tool_use["input"] = json.loads(tool_input_json)
                            except json.JSONDecodeError:
                                current_tool_use["input"] = {}
                        yield {
                            "type": "tool_use",
                            "tool_use": current_tool_use,
                        }
                        current_tool_use = None
                        tool_input_json = ""

                elif event.type == "message_stop":
                    yield {
                        "type": "message_complete",
                        "stop_reason": stream.current_message_snapshot.stop_reason,
                    }

    async def _chat_stream_openai(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream a chat response from OpenAI."""
        import json

        model = self._get_model()
        openai_messages = []

        if system:
            openai_messages.append({"role": "system", "content": system})

        # Convert messages to OpenAI format
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        text_parts.append(f"Tool result: {block.get('content', '')}")
                content = "\n".join(text_parts) if text_parts else str(content)
            openai_messages.append({"role": role, "content": content})

        kwargs = {
            "model": model,
            "max_completion_tokens": max_tokens,  # OpenAI uses max_completion_tokens for newer models
            "messages": openai_messages,
            # Note: Newer OpenAI models only support temperature=1, omit to use default
            "stream": True,
        }

        if tools:
            openai_tools = []
            for tool in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    }
                })
            kwargs["tools"] = openai_tools

        current_tool_calls = {}

        client = self._get_openai_client()
        logger.info(f"[OpenAI] Starting stream with model {model}")
        async for chunk in await client.chat.completions.create(**kwargs):
            logger.debug(f"[OpenAI] Received chunk: {chunk}")
            if chunk.choices:
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason
                logger.info(f"[OpenAI] Delta - content: {delta.content is not None}, tool_calls: {delta.tool_calls is not None}, finish: {finish_reason}")

                # Handle text content
                if delta.content:
                    yield {
                        "type": "text_delta",
                        "text": delta.content,
                    }

                # Handle tool calls
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        idx = tool_call.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tool_call.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tool_call.id:
                            current_tool_calls[idx]["id"] = tool_call.id
                        if tool_call.function:
                            if tool_call.function.name:
                                current_tool_calls[idx]["name"] = tool_call.function.name
                            if tool_call.function.arguments:
                                current_tool_calls[idx]["arguments"] += tool_call.function.arguments
                                yield {
                                    "type": "tool_use_delta",
                                    "partial_json": tool_call.function.arguments,
                                }

                # Handle finish
                if chunk.choices[0].finish_reason:
                    # Emit completed tool calls
                    for tc in current_tool_calls.values():
                        try:
                            input_data = json.loads(tc["arguments"]) if tc["arguments"] else {}
                        except json.JSONDecodeError:
                            input_data = {}
                        yield {
                            "type": "tool_use",
                            "tool_use": {
                                "id": tc["id"],
                                "name": tc["name"],
                                "input": input_data,
                            },
                        }

                    yield {
                        "type": "message_complete",
                        "stop_reason": "end_turn" if chunk.choices[0].finish_reason == "stop" else chunk.choices[0].finish_reason,
                    }

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse a Claude API response."""
        result = {
            "id": response.id,
            "model": response.model,
            "stop_reason": response.stop_reason,
            "content": [],
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }

        for block in response.content:
            if block.type == "text":
                result["content"].append({
                    "type": "text",
                    "text": block.text,
                })
            elif block.type == "tool_use":
                result["content"].append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return result

    async def handle_tool_result(
        self,
        messages: List[Dict[str, Any]],
        tool_use_id: str,
        tool_result: Any,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Continue conversation with a tool result."""
        # Add tool result to messages
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": str(tool_result),
            }],
        })

        return await self.chat(
            messages=messages,
            system=system,
            tools=tools,
        )

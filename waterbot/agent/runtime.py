"""Conversational agent runtime for WaterBot."""

import json
import logging
from typing import Any, Dict, List, Optional

from ..actions import ActionEngine
from .memory import AgentMemory

logger = logging.getLogger("waterbot.agent")


class AgentRuntime:
    """Coordinate memory, model calls, tool dispatch, and audit history."""

    def __init__(
        self,
        client: Any,
        model: str,
        memory: Optional[AgentMemory] = None,
        action_engine: Optional[ActionEngine] = None,
    ) -> None:
        """Initialize the runtime."""
        self.client = client
        self.model = model
        self.memory = memory or AgentMemory()
        self.action_engine = action_engine or ActionEngine(self.memory)

    async def process(
        self,
        message: str,
        channel_id: str = "default",
        author_id: Optional[str] = None,
        author_name: Optional[str] = None,
    ) -> str:
        """Process a user message with persistent channel context."""
        if not self.client:
            return "OpenAI is not configured. Please set OPENAI_API_KEY in your .env file."

        self.memory.record_message(channel_id, "user", message, author_id, author_name)
        context = self.memory.get_context(channel_id)
        feedback = self.memory.get_recent_feedback(limit=5)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": _system_message(context, feedback)},
            {"role": "user", "content": message},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=get_agent_tools(),
            tool_choice="auto",
            max_tokens=1200,
            temperature=0.4,
        )

        response_message = response.choices[0].message
        messages.append(_assistant_message_param(response_message))

        max_rounds = 5
        current_round = 0
        while response_message.tool_calls and current_round < max_rounds:
            current_round += 1
            logger.info("Agent tool call round %s", current_round)
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as exc:
                    tool_result = f"Invalid tool JSON for {function_name}: {exc}"
                else:
                    tool_result = self.execute_tool(function_name, function_args, channel_id)

                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_result,
                    }
                )

            next_response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=get_agent_tools(),
                tool_choice="auto",
                max_tokens=1200,
                temperature=0.4,
            )
            response_message = next_response.choices[0].message
            messages.append(_assistant_message_param(response_message))

        final_response = response_message.content or "I completed the requested action."
        self.memory.record_message(channel_id, "assistant", final_response, author_name="WaterBot")
        return final_response

    def execute_tool(self, function_name: str, arguments: Dict[str, Any], channel_id: str = "default") -> str:
        """Execute one model-requested tool."""
        if function_name == "preview_action":
            result = self.action_engine.preview_action(arguments["action_type"], arguments.get("arguments", {}))
        elif function_name == "execute_action":
            result = self.action_engine.execute_action(
                arguments["action_type"],
                arguments.get("arguments", {}),
                source="agent",
                channel_id=channel_id,
                require_confirmation=True,
            )
        elif function_name == "get_recent_context":
            return json.dumps(self.memory.get_context(channel_id), indent=2)
        elif function_name == "get_policy_decision_history":
            result = self.action_engine.execute_action(
                "get_policy_decision_history",
                {"device": arguments.get("device")},
                source="agent",
                channel_id=channel_id,
                require_confirmation=False,
            )
        elif function_name == "record_user_feedback":
            args = dict(arguments)
            args["channel_id"] = channel_id
            result = self.action_engine.execute_action(
                "record_user_feedback",
                args,
                source="agent",
                channel_id=channel_id,
                require_confirmation=False,
            )
        else:
            result = self.action_engine.execute_action(
                function_name,
                arguments,
                source="agent",
                channel_id=channel_id,
                require_confirmation=True,
            )
        return result.message


def get_agent_tools() -> List[Dict[str, Any]]:
    """Return generic agent tools plus legacy action names."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "preview_action",
                "description": "Preview a WaterBot action without executing it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action_type": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["action_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_action",
                "description": (
                    "Execute a WaterBot action. Risky actions return a confirmation "
                    "token instead of executing immediately."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action_type": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["action_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_recent_context",
                "description": "Get persistent channel memory and recent messages.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_policy_decision_history",
                "description": "Explain recent automatic watering decisions for all devices or one device.",
                "parameters": {
                    "type": "object",
                    "properties": {"device": {"type": "string"}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "record_user_feedback",
                "description": "Record user feedback such as too wet, too dry, or skipped intentionally.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string"},
                        "feedback": {"type": "string"},
                    },
                    "required": ["feedback"],
                },
            },
        },
    ]

    for name in [
        "get_device_status",
        "turn_device_on",
        "turn_device_off",
        "add_schedule",
        "remove_schedule",
        "replace_device_schedule",
        "clear_device_schedule",
        "get_schedules",
        "upsert_policy_schedule",
        "create_every_n_days_cycle",
        "remove_policy_schedule",
        "get_policy_schedules",
        "get_weather_context",
        "get_current_time",
        "get_ip_addresses",
        "test_notification",
    ]:
        tools.append(_legacy_tool_schema(name))

    return tools


def _legacy_tool_schema(name: str) -> Dict[str, Any]:
    """Return a permissive schema for legacy action-name tools."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Execute WaterBot action {name}.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
        },
    }


def _assistant_message_param(message: Any) -> Dict[str, Any]:
    """Convert an SDK assistant message object into a chat message param."""
    param: Dict[str, Any] = {"role": "assistant", "content": getattr(message, "content", None)}
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        param["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in tool_calls
        ]
    return param


def _system_message(context: Dict[str, Any], feedback: Optional[List[Dict[str, Any]]] = None) -> str:
    summary = context.get("summary", {}).get("summary") or "No prior channel summary."
    recent_lines = []
    for item in context.get("recent_messages", []):
        speaker = item.get("author_name") or item.get("role")
        recent_lines.append(f"{speaker}: {item.get('content')}")
    recent = "\n".join(recent_lines) or "No recent messages."
    feedback_lines = []
    for item in feedback or []:
        target = f" for {item.get('device')}" if item.get("device") else ""
        feedback_lines.append(f"- {item.get('created_at')}{target}: {item.get('feedback')}")
    feedback_text = "\n".join(feedback_lines) or "No recent user feedback."

    return (
        "You are WaterBot, a careful conversational agent for watering and GPIO control.\n\n"
        "Use persistent channel context to understand follow-up requests. Prefer tools over guessing. "
        "For risky or permanent changes, execute_action will return a confirmation token; when that "
        "happens, tell the user exactly what will happen and how to confirm or cancel.\n\n"
        "Risky actions include all-device actions, replacing or clearing schedules, saving or deleting "
        "flexible policies, and other permanent schedule changes. Automatic policy runs are allowed, "
        "but user-requested risky changes need confirmation.\n\n"
        "For 'why did it run/skip' questions, use get_policy_decision_history. For 'too wet', 'too dry', "
        "or similar feedback, call record_user_feedback.\n\n"
        f"Channel summary:\n{summary}\n\nRecent messages:\n{recent}\n\nRecent feedback:\n{feedback_text}"
    )

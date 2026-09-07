"""Decor host harness. Discovers and calls tools over MCP. Not LangGraph ToolNode."""

from __future__ import annotations

import json
from typing import Any

import anyio
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from mcp import Client

from app.config import get_settings
from app.flags import (
    AIConfigDefault,
    build_context,
    current_user_tier,
    get_completion_config,
    set_current_context_key,
)
from app.llm import get_llm
from app.logging import get_logger
from app.nodes.input_guard import input_guard
from app.prompts import AGENT_SYSTEM_PROMPT
from app.state import default_state
from mcp_servers.decor_design import server

log = get_logger(__name__)

# search_catalog is read-only. The other two change the project; we still
# execute them, then stop after request_approval so a human can commit.
MUTATING_TOOLS = frozenset({"update_project", "request_approval"})

# LaunchDarkly still ships the old specialist-router prompt. That prompt
# tells the model to invent IKEA prices. The job lives here until those
# AI Configs are rewritten for MCP.
TIER_NOTES = {
    "free": "Prefer lower-priced catalog rows that still fit the brief.",
    "premium": "Prefer higher-end catalog rows when the budget holds.",
}


def _schema_dict(schema: Any) -> dict:
    if schema is None:
        return {"type": "object", "properties": {}}
    if isinstance(schema, dict):
        return schema
    if hasattr(schema, "model_dump"):
        return schema.model_dump()
    return dict(schema)


def bindings_from_mcp_tools(tools: list) -> list[dict]:
    """Turn tools/list results into Claude bind_tools schemas."""
    bindings = []
    for tool in tools:
        bindings.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": _schema_dict(getattr(tool, "inputSchema", None)),
            }
        )
    return bindings


def parse_mcp_payload(result: Any) -> Any:
    if getattr(result, "structured_content", None):
        return result.structured_content
    content = getattr(result, "content", None) or []
    if content and getattr(content[0], "text", None):
        text = content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return ""


def inject_context_key(name: str, args: dict, context_key: str) -> dict:
    filled = dict(args)
    if name in {"update_project", "request_approval"} and "context_key" not in filled:
        filled["context_key"] = context_key
    return filled


def _final_text(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not (getattr(msg, "tool_calls", []) or []):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            return str(content)
    return ""


async def _read_project(client: Client, context_key: str) -> dict:
    resource = await client.read_resource(f"project://{context_key}")
    payload = parse_mcp_payload(resource)
    if isinstance(payload, dict) and "status" in payload:
        return payload
    if getattr(resource, "contents", None):
        return json.loads(resource.contents[0].text)
    return {}


async def _run(message: str, context_key: str) -> dict:
    settings = get_settings()
    set_current_context_key(context_key)

    guard = input_guard(default_state(message, context_key=context_key))
    if not guard.get("input_valid", True):
        reply = ""
        for msg in reversed(guard.get("messages") or []):
            if isinstance(msg, AIMessage):
                reply = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
        return {
            "response": reply,
            "metadata": {**guard.get("metadata", {}), "routed_to": "rejected"},
            "project": {},
        }

    context = build_context(context_key)
    default = AIConfigDefault(
        model=settings.default_model,
        system_prompt=AGENT_SYSTEM_PROMPT,
        max_tokens=settings.max_tokens,
    )
    cfg = get_completion_config("decor-agent-main", context, default)
    llm = get_llm(cfg.model, cfg.max_tokens, cfg.temperature)

    tool_calls_made: list[str] = []
    stop_reason = "direct"

    async with Client(server) as client:
        listed = await client.list_tools()
        bindings = bindings_from_mcp_tools(listed.tools)
        llm_with_tools = llm.bind_tools(bindings)

        project = await _read_project(client, context_key)
        messages: list = [
            HumanMessage(content=message),
        ]

        for iteration in range(1, settings.max_agent_iterations + 1):
            project = await _read_project(client, context_key)
            if cfg.system_prompt.strip() != AGENT_SYSTEM_PROMPT.strip():
                log.info(
                    "harness.host_job_prompt",
                    reason="launchdarkly_prompt_is_pre_mcp_wrapper",
                    ld_config=cfg.config_key,
                )
            tier_note = TIER_NOTES.get(current_user_tier() or "", "")
            system = (
                f"{AGENT_SYSTEM_PROMPT}\n"
                f"{tier_note}\n\n"
                f"## Current design project (`project://{context_key}`)\n"
                f"{json.dumps(project, indent=2)}"
            )
            turn = [SystemMessage(content=system), *messages]

            try:
                response = llm_with_tools.invoke(turn)
            except Exception:
                cfg.track_error()
                raise
            cfg.track_success()
            messages.append(response)

            calls = getattr(response, "tool_calls", []) or []
            if not calls:
                stop_reason = "awaiting_approval" if project.get("pending_approval") else "direct"
                if tool_calls_made:
                    stop_reason = (
                        "awaiting_approval" if project.get("pending_approval") else "complete"
                    )
                break

            for call in calls:
                name = call["name"]
                args = inject_context_key(name, call.get("args") or {}, context_key)
                log.info("harness.tools_call", tool=name, iteration=iteration)
                result = await client.call_tool(name, args)
                tool_calls_made.append(name)
                payload = parse_mcp_payload(result)
                messages.append(
                    ToolMessage(
                        content=json.dumps(payload) if not isinstance(payload, str) else payload,
                        tool_call_id=call.get("id") or name,
                        name=name,
                    )
                )
            if "request_approval" in [call["name"] for call in calls]:
                stop_reason = "awaiting_approval"
                break
        else:
            stop_reason = "max_iterations"

        project = await _read_project(client, context_key)

    routed_to = tool_calls_made[0] if tool_calls_made else "direct"
    metadata = {
        "routed_to": routed_to,
        "tool_calls_made": tool_calls_made,
        "stop_reason": stop_reason,
        "context_key": context_key,
        "source": "mcp_harness",
    }
    log.info(
        "harness.done",
        context_key=context_key,
        routed_to=routed_to,
        stop_reason=stop_reason,
        tools=tool_calls_made,
    )
    return {
        "response": _final_text(messages),
        "metadata": metadata,
        "project": project,
    }


async def run_agent_async(message: str, context_key: str = "anonymous") -> dict:
    """Host entry for FastAPI. Uses the already-running asyncio loop."""
    log.info("run_agent.start", context_key=context_key, message_len=len(message))
    return await _run(message, context_key)


def run_agent(message: str, context_key: str = "anonymous") -> dict:
    """Sync wrapper for tests and scripts. Do not call from an async route."""
    return anyio.run(run_agent_async, message, context_key)

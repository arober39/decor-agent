"""Decor host harness. Discovers and calls tools over MCP. Not LangGraph ToolNode."""

from __future__ import annotations

import json
import re
from typing import Any

from app.catalog import PRODUCTS, get_product, room_key, search_products

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
MUTATING_TOOLS = frozenset({"update_project", "request_approval", "apply_board"})
CONTEXT_TOOLS = frozenset({"update_project", "request_approval", "apply_board"})

# LaunchDarkly still ships the old specialist-router prompt. That prompt
# tells the model to invent IKEA prices. The job lives here until those
# AI Configs are rewritten for MCP.
TIER_NOTES = {
    "free": "Prefer lower-priced catalog rows that still fit the brief.",
    "premium": "Prefer higher-end catalog rows when the budget holds.",
}

APPLY_BOARD_PHRASES = (
    "sample board",
    "map the board",
    "map sample",
    "map the sample",
)

APPLY_BOARD_REFUSAL = {
    "error": (
        "apply_board is only for an explicit sample-board ask. "
        "Search the catalog and update_project add_spec instead."
    )
}


def asked_for_sample_board(message: str) -> bool:
    """True only when the user asked to map the sample board, not a room brief."""
    lower = (message or "").lower()
    return any(phrase in lower for phrase in APPLY_BOARD_PHRASES)


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
    if name in CONTEXT_TOOLS and "context_key" not in filled:
        filled["context_key"] = context_key
    return filled


_REVISION_VERBS = ("swap", "replace", "switch", "instead")
_DROP_VERBS = ("drop ", "remove ", "take off")
_WANT_WORDS = (
    "white",
    "brass",
    "black",
    "gray",
    "grey",
    "oak",
    "walnut",
    "jute",
    "rust",
    "linen",
    "velvet",
    "charcoal",
    "olive",
    "speckled",
    "ivory",
    "ceramic",
    "marble",
    "mohair",
    "cheaper",
)
_CATEGORY_HINTS = (
    ("coffee table", "table"),
    ("floor lamp", "lighting"),
    ("table lamp", "lighting"),
    ("lighting", "lighting"),
    ("lamp", "lighting"),
    ("sofa", "sofa"),
    ("couch", "sofa"),
    ("rug", "rug"),
    ("chair", "chair"),
    ("table", "table"),
    ("desk", "desk"),
    ("bed", "bed"),
    ("paint", "paint"),
    ("mirror", "decor"),
    ("drape", "drapery"),
    ("curtain", "drapery"),
    ("drapery", "drapery"),
)


def parse_revision_intent(message: str) -> dict | None:
    """Swap/drop language the host can honor without waiting on the model."""
    lower = f" {message.lower()} "
    kind = ""
    if any(verb in lower for verb in _REVISION_VERBS):
        kind = "swap"
    elif any(verb in lower for verb in _DROP_VERBS):
        kind = "drop"
    if not kind:
        return None
    category = ""
    for hint, mapped in _CATEGORY_HINTS:
        if hint in lower:
            category = mapped
            break
    return {"kind": kind, "category": category}


def parse_job_facts(message: str) -> dict:
    """Facts the host already knows from this turn. Not a model guess."""
    facts: dict[str, Any] = {}
    money = re.search(r"\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)", message)
    if money:
        facts["budget_dollars"] = float(money.group(1).replace(",", ""))
    dims = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)", message, re.I)
    if dims:
        facts["width_ft"] = float(dims.group(1))
        facts["length_ft"] = float(dims.group(2))
    lower = message.lower()
    for room in ("living", "bedroom", "kitchen", "dining", "bathroom", "office"):
        if room in lower:
            facts["room_type"] = room
            facts["room_name"] = room if room in {"kitchen", "office"} else f"{room} room"
            break
    if "mid-century" in lower or "midcentury" in lower:
        facts["style_preferences"] = "mid-century"
    return facts


def inject_job_facts(name: str, args: dict, context_key: str, user_message: str) -> dict:
    filled = inject_context_key(name, args, context_key)
    if name != "update_project":
        return filled
    facts = parse_job_facts(user_message)
    action = filled.get("action")
    if action == "set_budget" and filled.get("budget_dollars") is None and "budget_dollars" in facts:
        filled["budget_dollars"] = facts["budget_dollars"]
    if action == "upsert_room":
        if not str(filled.get("room_name") or "").strip() and facts.get("room_name"):
            filled["room_name"] = facts["room_name"]
        if filled.get("width_ft") is None and "width_ft" in facts:
            filled["width_ft"] = facts["width_ft"]
        if filled.get("length_ft") is None and "length_ft" in facts:
            filled["length_ft"] = facts["length_ft"]
        if not filled.get("room_type") and facts.get("room_type"):
            filled["room_type"] = facts["room_type"]
    if action == "set_brief" and not filled.get("style_preferences") and facts.get("style_preferences"):
        filled["style_preferences"] = facts["style_preferences"]
    return filled


def search_skus_from_messages(messages: list) -> list[str]:
    seen: list[str] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        if getattr(msg, "name", "") != "search_catalog":
            continue
        try:
            payload = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        for row in payload.get("matches") or []:
            sku = (row or {}).get("sku")
            if sku and sku not in seen:
                seen.append(sku)
    return seen


def skus_named_in_text(text: str, skus: list[str]) -> list[str]:
    named: list[str] = []
    blob = text.lower()
    candidates = skus or [product.sku for product in PRODUCTS]
    for sku in candidates:
        product = get_product(sku)
        if product is None:
            continue
        if sku.lower() in blob or product.name.lower() in blob:
            named.append(sku)
    return named


def _project_room_name(project: dict, fallback: str = "living room") -> str:
    rooms = project.get("rooms") or {}
    if len(rooms) == 1:
        room = next(iter(rooms.values()))
        if isinstance(room, dict) and room.get("name"):
            return room["name"]
    return fallback


def _project_room_type(project: dict) -> str:
    rooms = project.get("rooms") or {}
    if len(rooms) == 1:
        room = next(iter(rooms.values()))
        if isinstance(room, dict) and room.get("room_type"):
            return room_key(room["room_type"])
    return room_key(_project_room_name(project))


def _wanted_looks(message: str) -> list[str]:
    lower = f" {message.lower()} "
    return [word for word in _WANT_WORDS if f" {word} " in lower]


def _matches_look(product, wants: list[str]) -> bool:
    if not wants or wants == ["cheaper"]:
        return True
    blob = " ".join((product.color, product.name, *product.tags)).lower()
    looks = [word for word in wants if word != "cheaper"]
    return all(word in blob for word in looks)


def _revision_hits(user_message: str, category: str, messages: list, room_type: str) -> list:
    found = search_skus_from_messages(messages)
    products = [get_product(sku) for sku in found]
    products = [item for item in products if item is not None]
    if not products:
        products = search_products(query=user_message, category=category, limit=8)
    if category:
        products = [item for item in products if item.category == category]
    if room_type:
        products = [item for item in products if room_type in item.room_types]
    wants = _wanted_looks(user_message)
    filtered = [item for item in products if _matches_look(item, wants)]
    return filtered


async def _request_spec_approval(client: Client, context_key: str, summary: str) -> dict:
    await client.call_tool(
        "request_approval",
        {"context_key": context_key, "kind": "spec", "summary": summary},
    )
    return await _read_project(client, context_key)


async def persist_revision(
    client: Client,
    context_key: str,
    user_message: str,
    messages: list,
    project: dict,
) -> tuple[dict, str | None]:
    """Honor swap/drop from inventory even when the model skips tools."""
    intent = parse_revision_intent(user_message)
    if not intent:
        return project, None
    category = intent["category"]
    room_type = _project_room_type(project)
    hits = _revision_hits(user_message, category, messages, room_type)
    spec_items = project.get("spec_list") or []
    spec_skus = {item.get("sku") for item in spec_items}
    room = _project_room_name(project)
    named = skus_named_in_text(user_message, [item.sku for item in hits])

    if intent["kind"] == "drop":
        if not category:
            return project, None
        removed = [item for item in spec_items if item.get("category") == category]
        if not removed:
            return project, f"Nothing in {category} is on the list to drop."
        for item in removed:
            await client.call_tool(
                "update_project",
                {
                    "context_key": context_key,
                    "action": "remove_spec",
                    "sku": item["sku"],
                },
            )
        names = ", ".join(f"{item.get('name')} ({item.get('sku')})" for item in removed)
        project = await _request_spec_approval(
            client, context_key, f"Removed {names}."
        )
        return project, f"Removed {names} from the draft spec."

    if not category:
        already = [item for item in hits if item.sku in spec_skus]
        if already:
            match = already[0]
            project = await _request_spec_approval(
                client,
                context_key,
                f"{match.name} ({match.sku}) is already on the list.",
            )
            return (
                project,
                f"{match.name} ({match.sku}) is already on the shopping list. "
                f"Inventory color is {match.color}. There is no second {match.category} to swap in.",
            )
        return project, None

    already = [item for item in hits if item.sku in spec_skus]
    incoming = [item for item in hits if item.sku not in spec_skus]
    if named:
        incoming = [item for item in incoming if item.sku in named] or incoming
    if not incoming and already:
        match = already[0]
        project = await _request_spec_approval(
            client,
            context_key,
            f"{match.name} ({match.sku}) is already the {match.color} {match.category}.",
        )
        return (
            project,
            f"{match.name} ({match.sku}) is already on the shopping list. "
            f"Inventory color is {match.color}. There is no second {match.category} to swap in.",
        )

    if not incoming:
        wants = [word for word in _wanted_looks(user_message) if word != "cheaper"]
        look = " ".join(wants) or "matching"
        kind = category or "piece"
        return (
            project,
            f"Inventory has no {look} {kind} for this {room_type} room. "
            "I will not substitute a different room or invent a SKU.",
        )

    match = incoming[0]
    for item in spec_items:
        if item.get("category") == match.category and item.get("sku") != match.sku:
            await client.call_tool(
                "update_project",
                {
                    "context_key": context_key,
                    "action": "remove_spec",
                    "sku": item["sku"],
                },
            )
    await client.call_tool(
        "update_project",
        {
            "context_key": context_key,
            "action": "add_spec",
            "sku": match.sku,
            "room_name": room,
            "lane": "close",
            "why": f"Client swap to {match.color} {match.category}",
        },
    )
    project = await _request_spec_approval(
        client,
        context_key,
        f"Swapped {match.category} to {match.name} ({match.sku}).",
    )
    return project, f"Swapped the {match.category} to {match.name} ({match.sku})."


async def persist_talked_about_project(
    client: Client,
    context_key: str,
    user_message: str,
    messages: list,
    commentary: str,
) -> tuple[dict, str | None]:
    """Write project:// from this turn when the model searched but forgot to persist."""
    facts = parse_job_facts(user_message)
    if facts.get("budget_dollars") is not None:
        await client.call_tool(
            "update_project",
            {
                "context_key": context_key,
                "action": "set_budget",
                "budget_dollars": facts["budget_dollars"],
            },
        )
    if facts.get("room_name"):
        await client.call_tool(
            "update_project",
            {
                "context_key": context_key,
                "action": "upsert_room",
                "room_name": facts["room_name"],
                "room_type": facts.get("room_type") or "living",
                "width_ft": facts.get("width_ft"),
                "length_ft": facts.get("length_ft"),
            },
        )
    if facts.get("style_preferences"):
        await client.call_tool(
            "update_project",
            {
                "context_key": context_key,
                "action": "set_brief",
                "style_preferences": facts["style_preferences"],
            },
        )
    project = await _read_project(client, context_key)
    if parse_revision_intent(user_message):
        return await persist_revision(
            client, context_key, user_message, messages, project
        )
    found = search_skus_from_messages(messages)
    to_add = skus_named_in_text(commentary, found) or found[:4]
    room = facts.get("room_name") or _project_room_name(project)
    for sku in to_add:
        await client.call_tool(
            "update_project",
            {
                "context_key": context_key,
                "action": "add_spec",
                "sku": sku,
                "room_name": room,
            },
        )
    if to_add:
        log.info("harness.persisted_project", context_key=context_key, skus=to_add)
    return await _read_project(client, context_key), None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        bits: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type", "text") == "text":
                bits.append(part.get("text") or "")
            elif hasattr(part, "text"):
                bits.append(getattr(part, "text") or "")
        return "".join(bits).strip()
    return ""


def _final_text(messages: list) -> str:
    """Last non-empty model text, including preambles on tool-call turns."""
    texts: list[str] = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        text = _content_text(msg.content)
        if text:
            texts.append(text)
    return texts[-1] if texts else ""


def commentary_from_project(project: dict) -> str:
    """Host fallback when the model only emitted tool calls."""
    specs = project.get("spec_list") or []
    if specs:
        names = ", ".join(
            f"{item.get('name')} ({item.get('sku')})" for item in specs
        )
        return f"Draft spec is on the project: {names}. Approve when you are ready."
    budget = (project.get("budget") or {}).get("total_cents")
    rooms = project.get("rooms") or {}
    if budget or rooms:
        return "The project is updated. Check the panel — I will keep sourcing from the catalog."
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
    commentary = ""

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

            executed_apply_board = False
            for call in calls:
                name = call["name"]
                args = inject_job_facts(
                    name, call.get("args") or {}, context_key, message
                )
                log.info("harness.tools_call", tool=name, iteration=iteration)
                if name == "apply_board" and not asked_for_sample_board(message):
                    payload = APPLY_BOARD_REFUSAL
                    log.info("harness.apply_board_refused", reason="not_sample_board_ask")
                else:
                    result = await client.call_tool(name, args)
                    payload = parse_mcp_payload(result)
                    if name == "apply_board":
                        executed_apply_board = True
                tool_calls_made.append(name)
                messages.append(
                    ToolMessage(
                        content=json.dumps(payload) if not isinstance(payload, str) else payload,
                        tool_call_id=call.get("id") or name,
                        name=name,
                    )
                )
            called = [call["name"] for call in calls]
            if "request_approval" in called or executed_apply_board:
                stop_reason = "awaiting_approval"
                break
        else:
            stop_reason = "max_iterations"

        commentary = _final_text(messages)
        project, revision_reply = await persist_talked_about_project(
            client, context_key, message, messages, commentary
        )
        if revision_reply:
            commentary = revision_reply

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
    response = commentary or commentary_from_project(project)
    return {
        "response": response,
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

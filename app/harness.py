"""Decor host harness. Discovers and calls tools over MCP. Not LangGraph ToolNode."""

from __future__ import annotations

import json
import re
from typing import Any

from app.catalog import PRODUCTS, cheaper_in_room, get_product, room_key, search_products
from app import store

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
from app.flinch_gate import call_tool as flinch_call_tool
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


def _category_in(message: str) -> str:
    lower = f" {message.lower()} "
    for hint, mapped in _CATEGORY_HINTS:
        if hint in lower:
            return mapped
    return ""


def parse_revision_intent(message: str) -> dict | None:
    """Swap or drop a named piece. Bare "replace" is a new brief, not a SKU swap."""
    lower = f" {message.lower()} "
    category = _category_in(message)
    has_swap = any(verb in lower for verb in ("swap", "switch", "instead"))
    has_replace = "replace" in lower
    has_drop = any(verb in lower for verb in _DROP_VERBS)
    if has_drop and not has_swap and not (has_replace and category):
        kind = "drop"
    elif has_swap or (has_replace and category):
        kind = "swap"
    else:
        return None
    return {"kind": kind, "category": category}


def is_brief_confirmation(message: str) -> bool:
    """'yes replace' confirms a new room, budget, or style. It does not name a piece."""
    if parse_revision_intent(message):
        return False
    lower = " ".join((message or "").lower().split())
    return (
        re.fullmatch(
            r"(yes[, ]+)?(please )?replace( (it|the brief|the job|this|the project|the room|the budget|the style))?[.!]?",
            lower,
        )
        is not None
    )


def catalog_category(message: str) -> str:
    return _category_in(message)


def is_catalog_only_ask(message: str) -> bool:
    """A product search. Room and budget are for add_spec, not for this search."""
    if asked_for_sample_board(message) or parse_revision_intent(message) or is_brief_confirmation(message):
        return False
    if not catalog_category(message):
        return False
    facts = parse_job_facts(message)
    if facts.get("budget_dollars") is not None or facts.get("width_ft") is not None:
        return False
    lower = (message or "").lower()
    if any(token in lower for token in ("plan ", "design ", "outfit", "furnish")):
        return False
    return True


def _fold_style(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _style_match(product, style: str) -> bool:
    wanted = _fold_style(style)
    if not wanted:
        return False
    folded = _fold_style(product.style)
    return wanted in folded or folded in wanted


def _dollars(cents: int) -> str:
    return f"${cents / 100:.0f}"


def _user_named(message: str, product) -> bool:
    return product.sku in skus_named_in_text(message, [product.sku])


def _style_alternative(product, style: str, room_type: str):
    if _style_match(product, style):
        return None
    options = [
        other
        for other in PRODUCTS
        if other.category == product.category
        and other.sku != product.sku
        and _style_match(other, style)
        and (not room_type or room_type in other.room_types)
    ]
    if not options:
        return None

    def rank(other) -> tuple[int, int]:
        role = 0
        for token in ("coffee", "floor", "dining", "side", "night"):
            if token in product.name.lower() and token in other.name.lower():
                role = -1
        return (role, other.price_cents)

    options.sort(key=rank)
    return options[0]


def describe_job_facts(facts: dict) -> str:
    bits: list[str] = []
    if facts.get("width_ft") and facts.get("length_ft") and facts.get("room_name"):
        bits.append(
            f"{facts['width_ft']:g}×{facts['length_ft']:g} {facts['room_name']}"
        )
    elif facts.get("room_name"):
        bits.append(str(facts["room_name"]))
    if facts.get("budget_dollars") is not None:
        bits.append(f"${facts['budget_dollars']:g}")
    if facts.get("style_preferences"):
        bits.append(str(facts["style_preferences"]))
    if not bits:
        return ""
    return "Updated this job: " + ", ".join(bits) + "."


def job_facts_replace_existing(before: dict, facts: dict) -> bool:
    """True when this turn's room, budget, or style replaces facts already on the job."""
    if not facts:
        return False
    budget = (before.get("budget") or {}).get("total_cents")
    if facts.get("budget_dollars") is not None and budget is not None:
        if int(round(float(facts["budget_dollars"]) * 100)) != budget:
            return True
    style = (before.get("brief") or {}).get("style_preferences") or ""
    if facts.get("style_preferences") and style:
        if _fold_style(facts["style_preferences"]) != _fold_style(style):
            return True
    if facts.get("width_ft") is not None:
        for room in (before.get("rooms") or {}).values():
            if not isinstance(room, dict) or room.get("width_ft") is None:
                continue
            if float(room["width_ft"]) != float(facts["width_ft"]):
                return True
    return False


def style_budget_decision(
    skus: list[str],
    user_message: str,
    style: str,
    budget_cents: int | None,
    room_type: str,
) -> tuple[list[str], str | None]:
    """Keep the style match. Say so when a cheaper off-style SKU is what fits the cap."""
    if not style:
        return skus, None
    products = [item for item in (get_product(sku) for sku in skus) if item is not None]
    if not products:
        return skus, None
    replaced: list[tuple] = []
    chosen: list[str] = []
    for product in products:
        if _user_named(user_message, product) or _style_match(product, style):
            if product.sku not in chosen:
                chosen.append(product.sku)
            continue
        alternative = _style_alternative(product, style, room_type)
        if alternative is None:
            if product.sku not in chosen:
                chosen.append(product.sku)
            continue
        if alternative.sku not in chosen:
            chosen.append(alternative.sku)
        replaced.append((product, alternative))

    def total_of(sku_list: list[str]) -> int:
        return sum(item.price_cents for item in (get_product(sku) for sku in sku_list) if item)

    total = total_of(chosen)
    if replaced:
        bits = [
            (
                f"{on.name} ({on.sku}, {_dollars(on.price_cents)}, {on.style}) matches {style}. "
                f"{off.name} ({off.sku}, {_dollars(off.price_cents)}, {off.style}) "
                f"is the off-style option."
            )
            for off, on in replaced
        ]
        if budget_cents and total > budget_cents:
            lead = (
                "Style and budget do not both fit. "
                f"The style list is {_dollars(total)}, over the {_dollars(budget_cents)} cap."
            )
        else:
            lead = f"I kept the {style} match."
        return chosen, lead + " " + " ".join(bits) + " I kept the style match on the list."

    if not budget_cents or total <= budget_cents:
        return chosen, None
    offers: list[str] = []
    for product in products:
        if product.sku not in chosen or not _style_match(product, style):
            continue
        options = [
            other
            for other in cheaper_in_room(product.sku, room_type)
            if not _style_match(other, style)
        ]
        options.sort(key=lambda item: item.price_cents)
        fitting = [
            other
            for other in options
            if total - product.price_cents + other.price_cents <= budget_cents
        ]
        if not fitting:
            continue
        other = fitting[-1]
        offers.append(
            f"{product.name} ({product.sku}, {_dollars(product.price_cents)}, {product.style}) matches {style}. "
            f"{other.name} ({other.sku}, {_dollars(other.price_cents)}, {other.style}) "
            f"fits the {_dollars(budget_cents)} cap and is off-style."
        )
    if not offers:
        return chosen, None
    return (
        chosen,
        "Style and budget do not both fit. "
        f"The style list is {_dollars(total)}, over the {_dollars(budget_cents)} cap. "
        + " ".join(offers)
        + " I kept the style match on the list.",
    )


def catalog_only_result(message: str, context_key: str) -> dict:
    category = catalog_category(message) or "piece"
    matches = search_products(query=message, category=catalog_category(message), limit=4)
    if not matches:
        text = f"Inventory has nothing for that {category} search."
    else:
        bits = [
            f"{item.name} ({item.sku}, {_dollars(item.price_cents)})" for item in matches
        ]
        text = (
            "Catalog matches: "
            + "; ".join(bits)
            + ". Room and budget are only needed when you want these on a shopping list."
        )
    return {
        "response": text,
        "metadata": {
            "routed_to": "search_catalog",
            "tool_calls_made": ["search_catalog"],
            "stop_reason": "catalog_only",
            "context_key": context_key,
            "source": "mcp_harness",
        },
        "project": {},
    }


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


async def _request_spec_approval(
    client: Client, context_key: str, summary: str, stated_intent: str
) -> dict:
    await flinch_call_tool(
        client,
        "request_approval",
        {"context_key": context_key, "kind": "spec", "summary": summary},
        context_key=context_key,
        stated_intent=stated_intent,
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
            await flinch_call_tool(
                client,
                "update_project",
                {
                    "context_key": context_key,
                    "action": "remove_spec",
                    "sku": item["sku"],
                },
                context_key=context_key,
                stated_intent=user_message,
            )
        names = ", ".join(f"{item.get('name')} ({item.get('sku')})" for item in removed)
        project = await _request_spec_approval(
            client, context_key, f"Removed {names}.", user_message
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
                user_message,
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
            user_message,
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
            await flinch_call_tool(
                client,
                "update_project",
                {
                    "context_key": context_key,
                    "action": "remove_spec",
                    "sku": item["sku"],
                },
                context_key=context_key,
                stated_intent=user_message,
            )
    await flinch_call_tool(
        client,
        "update_project",
        {
            "context_key": context_key,
            "action": "add_spec",
            "sku": match.sku,
            "room_name": room,
            "lane": "close",
            "why": f"Client swap to {match.color} {match.category}",
        },
        context_key=context_key,
        stated_intent=user_message,
    )
    project = await _request_spec_approval(
        client,
        context_key,
        f"Swapped {match.category} to {match.name} ({match.sku}).",
        user_message,
    )
    return project, f"Swapped the {match.category} to {match.name} ({match.sku})."


async def _apply_job_facts(client: Client, context_key: str, user_message: str, facts: dict) -> None:
    if facts.get("budget_dollars") is not None:
        await flinch_call_tool(
            client,
            "update_project",
            {
                "context_key": context_key,
                "action": "set_budget",
                "budget_dollars": facts["budget_dollars"],
            },
            context_key=context_key,
            stated_intent=user_message,
        )
    if facts.get("room_name"):
        await flinch_call_tool(
            client,
            "update_project",
            {
                "context_key": context_key,
                "action": "upsert_room",
                "room_name": facts["room_name"],
                "room_type": facts.get("room_type") or "living",
                "width_ft": facts.get("width_ft"),
                "length_ft": facts.get("length_ft"),
            },
            context_key=context_key,
            stated_intent=user_message,
        )
    if facts.get("style_preferences"):
        await flinch_call_tool(
            client,
            "update_project",
            {
                "context_key": context_key,
                "action": "set_brief",
                "style_preferences": facts["style_preferences"],
            },
            context_key=context_key,
            stated_intent=user_message,
        )


async def persist_talked_about_project(
    client: Client,
    context_key: str,
    user_message: str,
    messages: list,
    commentary: str,
) -> tuple[dict, str | None]:
    """Write project:// from this turn when the model searched but forgot to persist."""
    facts_message = user_message
    confirming = is_brief_confirmation(user_message)
    if confirming:
        prior = store.peek_prior(context_key)
        if prior:
            facts_message = prior
    facts = parse_job_facts(facts_message)
    before = await _read_project(client, context_key)
    await _apply_job_facts(client, context_key, user_message, facts)
    project = await _read_project(client, context_key)
    if confirming:
        return project, describe_job_facts(facts) or "Updated this job."
    if parse_revision_intent(user_message):
        return await persist_revision(
            client, context_key, user_message, messages, project
        )
    found = search_skus_from_messages(messages)
    to_add = skus_named_in_text(commentary, found) or found[:4]
    style = facts.get("style_preferences") or ""
    budget_cents = None
    if facts.get("budget_dollars") is not None:
        budget_cents = int(round(float(facts["budget_dollars"]) * 100))
    elif (project.get("budget") or {}).get("total_cents") is not None:
        budget_cents = project["budget"]["total_cents"]
    room_type = facts.get("room_type") or _project_room_type(project)
    tradeoff = None
    if style:
        existing = [item.get("sku") for item in (project.get("spec_list") or []) if item.get("sku")]
        combined: list[str] = []
        for sku in [*existing, *to_add]:
            if sku not in combined:
                combined.append(sku)
        decided, tradeoff = style_budget_decision(
            combined, user_message, style, budget_cents, room_type
        )
        for sku in existing:
            if sku not in decided:
                await flinch_call_tool(
                    client,
                    "update_project",
                    {
                        "context_key": context_key,
                        "action": "remove_spec",
                        "sku": sku,
                    },
                    context_key=context_key,
                    stated_intent=user_message,
                )
        to_add = [sku for sku in decided if sku not in existing]
    room = facts.get("room_name") or _project_room_name(project)
    for sku in to_add:
        await flinch_call_tool(
            client,
            "update_project",
            {
                "context_key": context_key,
                "action": "add_spec",
                "sku": sku,
                "room_name": room,
            },
            context_key=context_key,
            stated_intent=user_message,
        )
    if to_add:
        log.info("harness.persisted_project", context_key=context_key, skus=to_add)
    project = await _read_project(client, context_key)
    update_note = (
        describe_job_facts(facts) if job_facts_replace_existing(before, facts) else None
    )
    note = " ".join(bit for bit in (update_note, tradeoff) if bit) or None
    return project, note


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
        store.remember_message(context_key, message)
        return {
            "response": reply,
            "metadata": {**guard.get("metadata", {}), "routed_to": "rejected"},
            "project": {},
        }

    if is_catalog_only_ask(message):
        store.remember_message(context_key, message)
        return catalog_only_result(message, context_key)

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
            fact_source = message
            if is_brief_confirmation(message):
                fact_source = store.peek_prior(context_key) or message
            for call in calls:
                name = call["name"]
                args = inject_job_facts(
                    name, call.get("args") or {}, context_key, fact_source
                )
                log.info("harness.tools_call", tool=name, iteration=iteration)
                if (
                    name == "update_project"
                    and is_brief_confirmation(message)
                    and args.get("action") in {"add_spec", "remove_spec"}
                ):
                    payload = {
                        "error": (
                            "replace without a piece updates the room, budget, and style. "
                            "It does not swap a SKU."
                        )
                    }
                    log.info("harness.brief_replace_refused_spec_edit")
                elif name == "apply_board" and not asked_for_sample_board(message):
                    payload = APPLY_BOARD_REFUSAL
                    log.info("harness.apply_board_refused", reason="not_sample_board_ask")
                else:
                    result = await flinch_call_tool(
                        client,
                        name,
                        args,
                        context_key=context_key,
                        stated_intent=message,
                    )
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
        store.remember_message(context_key, message)

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

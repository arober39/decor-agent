"""Project store. Memory by default; the server can persist rooms to a JSON file."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from app.board import resolve_sample_board
from app.catalog import cheaper_in_room, get_product
from app.events import SPEC_APPROVED, SPEC_SAVED, track
from app.project import (
    ApprovalKind,
    DesignProject,
    Room,
    SkippedPin,
    SpecItem,
    SpecLane,
    set_refresh_hook,
)


_lock = threading.Lock()
_projects: dict[str, DesignProject] = {}
_transcripts: dict[str, list[dict[str, str]]] = {}
_priors: dict[str, str] = {}
_persist_path: Path | None = None


def _guess_room_type(name: str) -> str:
    lower = name.lower()
    for room in ("living", "bedroom", "kitchen", "dining", "bathroom", "office"):
        if room in lower:
            return room
    return "living"


def _worth_saving(project: DesignProject) -> bool:
    brief = project.brief
    return bool(
        project.rooms
        or project.spec_list
        or project.budget_total_cents is not None
        or brief.lifestyle
        or brief.style_preferences
        or brief.keep
        or brief.avoid
        or project.board_pins
        or project.rejected
        or project.skipped
    )


def _save() -> None:
    if _persist_path is None:
        return
    _persist_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "projects": {
            key: project.model_dump(mode="json")
            for key, project in _projects.items()
            if _worth_saving(project)
        },
        "transcripts": {key: rows for key, rows in _transcripts.items() if rows},
        "priors": {key: text for key, text in _priors.items() if text},
    }
    _persist_path.write_text(json.dumps(payload, indent=2))


def _load() -> None:
    if _persist_path is None or not _persist_path.exists():
        return
    payload = json.loads(_persist_path.read_text())
    _projects.clear()
    for key, data in (payload.get("projects") or {}).items():
        _projects[key] = DesignProject.model_validate(data)
    _transcripts.clear()
    _transcripts.update(payload.get("transcripts") or {})
    _priors.clear()
    _priors.update(payload.get("priors") or {})


def enable_persist(path: str | Path | None = None) -> None:
    """Load rooms from disk and write them back on each mutation."""
    global _persist_path
    if path is None:
        _persist_path = Path(__file__).resolve().parents[1] / "data" / "projects.json"
    else:
        _persist_path = Path(path)
    _load()


def disable_persist() -> None:
    global _persist_path
    _persist_path = None


set_refresh_hook(lambda _project: _save())


def get_or_create(context_key: str) -> DesignProject:
    with _lock:
        project = _projects.get(context_key)
        if project is None:
            project = DesignProject(context_key=context_key)
            _projects[context_key] = project
        return project


def reset(context_key: str | None = None) -> None:
    """Clear memory. Does not delete a persist file; the next load reads it again."""
    with _lock:
        if context_key is None:
            _projects.clear()
            _transcripts.clear()
            _priors.clear()
        else:
            _projects.pop(context_key, None)
            _transcripts.pop(context_key, None)
            _priors.pop(context_key, None)


def peek_prior(context_key: str) -> str:
    return _priors.get(context_key, "")


def remember_message(context_key: str, message: str) -> None:
    text = (message or "").strip()
    if not text:
        return
    _priors[context_key] = text
    _save()


def transcript(context_key: str) -> list[dict[str, str]]:
    return list(_transcripts.get(context_key, []))


def append_transcript(context_key: str, role: str, text: str) -> None:
    cleaned = (text or "").strip()
    if not cleaned:
        return
    _transcripts.setdefault(context_key, []).append({"role": role, "text": cleaned})
    _save()


def list_rooms() -> list[dict]:
    rows = []
    keys = list(dict.fromkeys([*_projects.keys(), *_transcripts.keys()]))
    for key in keys:
        project = _projects.get(key)
        transcript_rows = _transcripts.get(key) or []
        if project and project.rooms:
            room = next(iter(project.rooms.values()))
            name = room.name
            status = project.status
            budget = project.budget_total_cents
        elif transcript_rows or (project is not None and _worth_saving(project)):
            name = "Untitled room"
            status = project.status if project is not None else "intake"
            budget = project.budget_total_cents if project is not None else None
        else:
            continue
        rows.append(
            {
                "context_key": key,
                "name": name,
                "status": status,
                "budget_cents": budget,
            }
        )
    rows.sort(key=lambda row: row["name"].lower())
    return rows


def create_room(name: str) -> DesignProject:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Room name is required")
    return upsert_room(
        str(uuid.uuid4()),
        name=cleaned,
        room_type=_guess_room_type(cleaned),
    )


def rename_room(context_key: str, name: str) -> DesignProject:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Room name is required")
    project = get_or_create(context_key)
    if len(project.rooms) != 1:
        return upsert_room(
            context_key,
            name=cleaned,
            room_type=_guess_room_type(cleaned),
        )
    _old_key, room = next(iter(project.rooms.items()))
    project.rooms.clear()
    room.name = cleaned
    room.room_type = _guess_room_type(cleaned)
    project.rooms[project.room_key(cleaned)] = room
    for item in project.spec_list:
        item.room = cleaned
    project.refresh_status()
    return project


def snapshot(context_key: str) -> dict:
    return get_or_create(context_key).as_public_dict()


def upsert_room(
    context_key: str,
    name: str,
    room_type: str = "living",
    width_ft: float | None = None,
    length_ft: float | None = None,
    existing_pieces: list[str] | None = None,
    style_notes: str | None = None,
) -> DesignProject:
    project = get_or_create(context_key)
    key = project.room_key(name)
    existing = project.rooms.get(key)
    project.rooms[key] = Room(
        name=name.strip(),
        room_type=room_type or (existing.room_type if existing else "living"),
        width_ft=width_ft if width_ft is not None else (existing.width_ft if existing else None),
        length_ft=length_ft if length_ft is not None else (existing.length_ft if existing else None),
        existing_pieces=existing_pieces if existing_pieces is not None else (existing.existing_pieces if existing else []),
        style_notes=style_notes if style_notes is not None else (existing.style_notes if existing else None),
    )
    project.refresh_status()
    return project


def set_brief(
    context_key: str,
    lifestyle: str = "",
    keep: list[str] | None = None,
    avoid: list[str] | None = None,
    style_preferences: str = "",
) -> DesignProject:
    project = get_or_create(context_key)
    if lifestyle:
        project.brief.lifestyle = lifestyle
    if keep is not None:
        project.brief.keep = keep
    if avoid is not None:
        project.brief.avoid = avoid
    if style_preferences:
        project.brief.style_preferences = style_preferences
    project.refresh_status()
    return project


def set_budget(context_key: str, budget_dollars: float) -> DesignProject:
    project = get_or_create(context_key)
    project.budget_total_cents = int(round(budget_dollars * 100))
    project.refresh_status()
    return project


def add_spec(
    context_key: str,
    sku: str,
    room_name: str,
    lane: SpecLane = "must",
    why: str = "",
) -> DesignProject:
    if lane == "skip":
        raise ValueError("skip lines are not spec items")
    product = get_product(sku)
    if product is None:
        raise ValueError(f"Unknown sku {sku}")
    project = get_or_create(context_key)
    target = room_name.strip()
    if not target:
        if len(project.rooms) == 1:
            target = next(iter(project.rooms.values())).name
        else:
            raise ValueError("room_name is required when the project has no single room")
    item = SpecItem(
        sku=product.sku,
        name=product.name,
        brand=product.brand,
        category=product.category,
        price_cents=product.price_cents,
        room=target,
        status="draft",
        lane=lane,
        why=why,
    )
    for existing in project.spec_list:
        if existing.sku == item.sku and existing.room.lower() == item.room.lower():
            existing.status = "draft"
            existing.price_cents = item.price_cents
            existing.lane = lane
            existing.why = why or existing.why
            project.refresh_status()
            return project
    project.spec_list.append(item)
    project.refresh_status()
    track(
        SPEC_SAVED,
        context_key,
        {"sku": item.sku, "lane": lane, "room": target},
        1,
    )
    return project


def apply_sample_board(
    context_key: str,
    room_name: str = "living room",
    budget_dollars: float = 2000,
) -> DesignProject:
    """Host/MCP entry: curated pins → must/close spec lines + skip list."""
    upsert_room(context_key, name=room_name, room_type="living")
    set_budget(context_key, budget_dollars)
    set_brief(
        context_key,
        lifestyle=f"{room_name} from a warm-linen board",
        style_preferences="warm whites, oak, rust ground",
    )
    project = get_or_create(context_key)
    decisions = resolve_sample_board()
    project.board_pins = [row["label"] for row in decisions]
    project.skipped = []
    for row in decisions:
        if row["lane"] == "skip" or not row["sku"]:
            project.skipped.append(SkippedPin(label=row["label"], why=row["why"]))
            continue
        add_spec(
            context_key,
            row["sku"],
            room_name,
            lane=row["lane"],
            why=row["why"],
        )
    project = get_or_create(context_key)
    if project.over_budget and project.budget_total_cents is not None:
        over = project.planned_cents - project.budget_total_cents
        cap = project.budget_total_cents
        summary = (
            f"${over / 100:.0f} over the ${cap / 100:.0f} cap. "
            "Drop an optional line or swap to a cheaper catalog SKU."
        )
    else:
        summary = "Board mapped to catalog. Approve to commit keep and optional lines."
    request_approval(context_key, "spec", summary)
    return get_or_create(context_key)


def _room_type(context_key: str) -> str:
    project = get_or_create(context_key)
    if len(project.rooms) == 1:
        return next(iter(project.rooms.values())).room_type
    return "living"


def _room_name(context_key: str) -> str:
    project = get_or_create(context_key)
    if len(project.rooms) == 1:
        return next(iter(project.rooms.values())).name
    return "living room"


def drop_spec(context_key: str, sku: str) -> DesignProject:
    project = get_or_create(context_key)
    item = next((row for row in project.spec_list if row.sku == sku), None)
    if item is None:
        raise ValueError(f"No spec line for {sku}")
    remove_spec(context_key, sku)
    request_approval(context_key, "spec", f"Removed {item.name} ({item.sku}).")
    return get_or_create(context_key)


def swap_spec(context_key: str, sku: str, to_sku: str) -> DesignProject:
    current = get_product(sku)
    incoming = get_product(to_sku)
    if current is None or incoming is None:
        raise ValueError("Unknown sku")
    room = _room_type(context_key)
    if incoming.category != current.category:
        raise ValueError("Swap has to stay in the same category")
    if room and room not in incoming.room_types:
        raise ValueError(f"{incoming.name} is not a {room} piece")
    project = get_or_create(context_key)
    existing = next((row for row in project.spec_list if row.sku == sku), None)
    lane = existing.lane if existing else "close"
    remove_spec(context_key, sku)
    add_spec(
        context_key,
        to_sku,
        _room_name(context_key),
        lane=lane,
        why=f"Cheaper catalog SKU than {current.name}",
    )
    request_approval(
        context_key,
        "spec",
        f"Swapped {current.name} for {incoming.name} ({incoming.sku}).",
    )
    return get_or_create(context_key)


def fit_budget(context_key: str) -> DesignProject:
    """Fit the cap from inventory: drop close lines, else a cheaper same-room SKU."""
    dropped: list[str] = []
    for _ in range(12):
        project = get_or_create(context_key)
        if not project.over_budget or project.budget_total_cents is None:
            if dropped:
                request_approval(
                    context_key,
                    "spec",
                    "Dropped " + ", ".join(dropped) + " to fit the cap.",
                )
            else:
                request_approval(context_key, "spec", "The list already fits the cap.")
            return project
        over = project.planned_cents - project.budget_total_cents
        room = _room_type(context_key)
        close = [item for item in project.spec_list if item.lane == "close"]
        close.sort(key=lambda item: item.price_cents)
        covering = [item for item in close if item.price_cents >= over]
        if covering:
            dropped.append(f"{covering[0].name} ({covering[0].sku})")
            drop_spec(context_key, covering[0].sku)
            continue
        swapped = False
        for item in list(get_or_create(context_key).spec_list):
            if item.lane != "close":
                continue
            for option in cheaper_in_room(item.sku, room):
                if item.price_cents - option.price_cents >= over:
                    swap_spec(context_key, item.sku, option.sku)
                    swapped = True
                    break
            if swapped:
                break
        if swapped:
            return get_or_create(context_key)
        if close:
            dropped.append(f"{close[0].name} ({close[0].sku})")
            drop_spec(context_key, close[0].sku)
            continue
        break
    return get_or_create(context_key)


def raise_budget_to_planned(context_key: str) -> DesignProject:
    project = get_or_create(context_key)
    if not project.planned_cents:
        raise ValueError("Nothing planned to raise the cap to")
    set_budget(context_key, project.planned_cents / 100)
    request_approval(
        context_key,
        "budget",
        f"Cap raised to ${project.planned_cents / 100:.0f} to match the list.",
    )
    return get_or_create(context_key)


def remove_spec(context_key: str, sku: str) -> DesignProject:
    project = get_or_create(context_key)
    project.spec_list = [item for item in project.spec_list if item.sku != sku]
    project.refresh_status()
    return project


def request_approval(context_key: str, kind: ApprovalKind, summary: str) -> DesignProject:
    project = get_or_create(context_key)
    project.pending_approval = True
    project.pending_approval_kind = kind
    project.pending_approval_summary = summary
    project.refresh_status()
    return project


def approve(context_key: str, kind: ApprovalKind | None = None) -> DesignProject:
    project = get_or_create(context_key)
    resolved = kind or project.pending_approval_kind or "spec"
    if resolved == "spec":
        for item in project.spec_list:
            if item.status == "draft":
                item.status = "committed"
                track(
                    SPEC_APPROVED,
                    context_key,
                    {"sku": item.sku, "lane": item.lane, "room": item.room},
                    1,
                )
    project.approvals[resolved] = True
    project.pending_approval = False
    project.pending_approval_kind = None
    project.pending_approval_summary = ""
    project.refresh_status()
    return project


def reject(context_key: str, reason: str = "") -> DesignProject:
    project = get_or_create(context_key)
    if reason:
        project.rejected.append(reason)
    project.pending_approval = False
    project.pending_approval_kind = None
    project.pending_approval_summary = ""
    project.refresh_status()
    return project

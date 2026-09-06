"""In-memory project store. Lives behind the MCP server, not the chat host."""

from __future__ import annotations

import threading

from app.catalog import get_product
from app.project import ApprovalKind, DesignProject, Room, SpecItem


_lock = threading.Lock()
_projects: dict[str, DesignProject] = {}


def get_or_create(context_key: str) -> DesignProject:
    with _lock:
        project = _projects.get(context_key)
        if project is None:
            project = DesignProject(context_key=context_key)
            _projects[context_key] = project
        return project


def reset(context_key: str | None = None) -> None:
    with _lock:
        if context_key is None:
            _projects.clear()
        else:
            _projects.pop(context_key, None)


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


def add_spec(context_key: str, sku: str, room_name: str) -> DesignProject:
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
    )
    for existing in project.spec_list:
        if existing.sku == item.sku and existing.room.lower() == item.room.lower():
            existing.status = "draft"
            existing.price_cents = item.price_cents
            project.refresh_status()
            return project
    project.spec_list.append(item)
    project.refresh_status()
    return project


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

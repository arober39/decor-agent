"""Design project models. The job lives here, not in chat history."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ApprovalKind = Literal["concept", "budget", "spec"]
SpecStatus = Literal["draft", "committed"]
SpecLane = Literal["must", "close", "skip"]
ProjectStatus = Literal["intake", "planning", "awaiting_approval", "complete"]

_after_refresh = None


def set_refresh_hook(fn) -> None:
    """Store registers this so a mutation can be written to disk."""
    global _after_refresh
    _after_refresh = fn


class Room(BaseModel):
    name: str
    room_type: str = "living"
    width_ft: float | None = None
    length_ft: float | None = None
    existing_pieces: list[str] = Field(default_factory=list)
    style_notes: str | None = None
    # New field for migration: home_id is None for legacy, set for new organization
    home_id: str | None = None

    def get_home_id(self, context_key: str) -> str:
        """Get the home ID for this room (returns context_key if not explicitly set)."""
        return self.home_id or context_key


class Brief(BaseModel):
    lifestyle: str = ""
    keep: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    style_preferences: str = ""


class SpecItem(BaseModel):
    sku: str
    name: str
    brand: str
    category: str
    price_cents: int
    room: str
    qty: int = 1
    status: SpecStatus = "draft"
    lane: SpecLane = "must"
    why: str = ""


class CartItem(BaseModel):
    """A held piece. It is not on the spec and it does not spend budget."""

    sku: str
    name: str
    price_cents: int
    qty: int = 1


class SkippedPin(BaseModel):
    label: str
    why: str = ""


class DesignProject(BaseModel):
    context_key: str
    brief: Brief = Field(default_factory=Brief)
    # Updated: allow `rooms` to model home-aware structure when migration is on
    # - pre-migration: rooms is {room_key: Room} (room_key = name.lower())
    # - post-migration: rooms is {(home_id, room_key): Room} (room_key = name.lower(), home_id stable)
    rooms: dict | None = Field(default_factory=dict)
    spec_list: list[SpecItem] = Field(default_factory=list)
    cart: list[CartItem] = Field(default_factory=list)
    skipped: list[SkippedPin] = Field(default_factory=list)
    board_pins: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    budget_total_cents: int | None = None
    pending_approval: bool = False
    pending_approval_kind: ApprovalKind | None = None
    pending_approval_summary: str = ""
    approvals: dict[str, bool] = Field(
        default_factory=lambda: {"concept": False, "budget": False, "spec": False}
    )
    status: ProjectStatus = "intake"

    @field_validator("rooms", mode="before")
    @classmethod
    def _coerce_rooms(cls, value):
        """Rebuild Room models after a JSON reload (keys may be legacy or home-aware)."""
        if not value:
            return {}
        return {
            key: Room.model_validate(room) if isinstance(room, dict) else room
            for key, room in value.items()
        }

    def get_rooms_by_home(self, context_key: str) -> dict[str, dict[str, Room]]:
        """
        Returns a mapping: {home_id: {room_key: Room, ...}}
        - If migration has not occurred, all rooms are in context_key.
        - If migration HAS occurred, rooms is {(home_id, room_key): Room}
        """
        # Dynamically import flag so we don't break model import
        try:
            from app.flags import (
                get_flag,
                build_context,
                DECORA_ROOM_HOME_MIGRATION_FLAG,
                DECORA_ROOM_HOME_MIGRATION_FLAG_DEFAULT,
            )
        except ImportError:
            # fallback for static analysis
            def get_flag(*a, **kw):
                return False

            def build_context(context_key):
                return {"key": context_key}

            DECORA_ROOM_HOME_MIGRATION_FLAG = "decora-room-home-migration"
            DECORA_ROOM_HOME_MIGRATION_FLAG_DEFAULT = False
        migration_on = get_flag(
            DECORA_ROOM_HOME_MIGRATION_FLAG,
            build_context(context_key),
            default=DECORA_ROOM_HOME_MIGRATION_FLAG_DEFAULT,
        )
        if not migration_on:
            # Legacy: one home (context_key), arbitrary mapping: {room_key: Room}
            return {context_key: dict(self.rooms)}
        # Migration: keys are (home_id, room_key)
        by_home = {}
        for key, room in self.rooms.items():
            if isinstance(key, tuple) and len(key) == 2:
                home_id, room_key = key
            else:
                # This should not occur if migration code consistent, fallback to context_key
                home_id, room_key = context_key, key
            by_home.setdefault(home_id, {})[room_key] = room
        return by_home

    def rooms_for_home(self, home_id: str, context_key: str) -> dict[str, Room]:
        by_home = self.get_rooms_by_home(context_key)
        return by_home.get(home_id, {})

    def all_rooms(self, context_key: str) -> list[Room]:
        """Return all Room objects in the project (for migration or summary ops)."""
        result = []
        for home_rooms in self.get_rooms_by_home(context_key).values():
            result.extend(home_rooms.values())
        return result

    @property
    def committed_cents(self) -> int:
        return sum(
            item.price_cents * item.qty
            for item in self.spec_list
            if item.status == "committed"
        )

    @property
    def draft_cents(self) -> int:
        return sum(
            item.price_cents * item.qty
            for item in self.spec_list
            if item.status == "draft"
        )

    @property
    def cart_cents(self) -> int:
        return sum(item.price_cents * item.qty for item in self.cart)

    @property
    def remaining_cents(self) -> int | None:
        if self.budget_total_cents is None:
            return None
        return self.budget_total_cents - self.committed_cents

    @property
    def planned_cents(self) -> int:
        return self.committed_cents + self.draft_cents

    @property
    def over_budget(self) -> bool:
        if self.budget_total_cents is None:
            return False
        return self.planned_cents > self.budget_total_cents

    def room_key(self, name: str) -> str:
        return name.strip().lower()

    def refresh_status(self) -> None:
        if self.pending_approval:
            self.status = "awaiting_approval"
        elif self.approvals.get("spec"):
            self.status = "complete"
        elif (
            self.rooms
            or self.spec_list
            or self.brief.lifestyle
            or self.budget_total_cents
        ):
            self.status = "planning"
        else:
            self.status = "intake"
        if _after_refresh is not None:
            _after_refresh(self)

    def as_public_dict(self) -> dict:
        from app.board import pin_image_url
        from app.catalog import catalog_image_url, cheaper_in_room, get_product

        room_type = "living"
        if len(self.rooms) == 1:
            room_type = next(iter(self.rooms.values())).room_type
        specs = []
        for item in self.spec_list:
            row = item.model_dump()
            row["image_url"] = catalog_image_url(item.sku)
            product = get_product(item.sku)
            row["color"] = product.color if product else ""
            row["cheaper"] = [
                {
                    "sku": option.sku,
                    "name": option.name,
                    "price_cents": option.price_cents,
                    "color": option.color,
                }
                for option in cheaper_in_room(item.sku, room_type)[:2]
            ]
            specs.append(row)
        over_cents = 0
        if self.over_budget and self.budget_total_cents is not None:
            over_cents = self.planned_cents - self.budget_total_cents
        return {
            "context_key": self.context_key,
            "status": self.status,
            "brief": self.brief.model_dump(),
            "rooms": {key: room.model_dump() for key, room in self.rooms.items()},
            "spec_list": specs,
            "cart": [
                {
                    **item.model_dump(),
                    "image_url": catalog_image_url(item.sku),
                }
                for item in self.cart
            ],
            "cart_cents": self.cart_cents,
            "skipped": [item.model_dump() for item in self.skipped],
            "board_pins": list(self.board_pins),
            "board": [
                {"label": label, "image_url": pin_image_url(label)}
                for label in self.board_pins
            ],
            "rejected": list(self.rejected),
            "budget": {
                "total_cents": self.budget_total_cents,
                "committed_cents": self.committed_cents,
                "draft_cents": self.draft_cents,
                "planned_cents": self.planned_cents,
                "remaining_cents": self.remaining_cents,
                "over_budget": self.over_budget,
                "over_cents": over_cents,
            },
            "pending_approval": self.pending_approval,
            "pending_approval_kind": self.pending_approval_kind,
            "pending_approval_summary": self.pending_approval_summary,
            "approvals": dict(self.approvals),
        }

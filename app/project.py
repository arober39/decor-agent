"""Design project models. The job lives here, not in chat history."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ApprovalKind = Literal["concept", "budget", "spec"]
SpecStatus = Literal["draft", "committed"]
SpecLane = Literal["must", "close", "skip"]
ProjectStatus = Literal["intake", "planning", "awaiting_approval", "complete"]


class Room(BaseModel):
    name: str
    room_type: str = "living"
    width_ft: float | None = None
    length_ft: float | None = None
    existing_pieces: list[str] = Field(default_factory=list)
    style_notes: str | None = None


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
    status: SpecStatus = "draft"
    lane: SpecLane = "must"
    why: str = ""


class SkippedPin(BaseModel):
    label: str
    why: str = ""


class DesignProject(BaseModel):
    context_key: str
    brief: Brief = Field(default_factory=Brief)
    rooms: dict[str, Room] = Field(default_factory=dict)
    spec_list: list[SpecItem] = Field(default_factory=list)
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

    @property
    def committed_cents(self) -> int:
        return sum(item.price_cents for item in self.spec_list if item.status == "committed")

    @property
    def draft_cents(self) -> int:
        return sum(item.price_cents for item in self.spec_list if item.status == "draft")

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
        elif self.rooms or self.spec_list or self.brief.lifestyle or self.budget_total_cents:
            self.status = "planning"
        else:
            self.status = "intake"

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

"""Design project models. The job lives here, not in chat history."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ApprovalKind = Literal["concept", "budget", "spec"]
SpecStatus = Literal["draft", "committed"]
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


class DesignProject(BaseModel):
    context_key: str
    brief: Brief = Field(default_factory=Brief)
    rooms: dict[str, Room] = Field(default_factory=dict)
    spec_list: list[SpecItem] = Field(default_factory=list)
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
        return {
            "context_key": self.context_key,
            "status": self.status,
            "brief": self.brief.model_dump(),
            "rooms": {key: room.model_dump() for key, room in self.rooms.items()},
            "spec_list": [item.model_dump() for item in self.spec_list],
            "rejected": list(self.rejected),
            "budget": {
                "total_cents": self.budget_total_cents,
                "committed_cents": self.committed_cents,
                "draft_cents": self.draft_cents,
                "remaining_cents": self.remaining_cents,
            },
            "pending_approval": self.pending_approval,
            "pending_approval_kind": self.pending_approval_kind,
            "pending_approval_summary": self.pending_approval_summary,
            "approvals": dict(self.approvals),
        }

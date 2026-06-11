"""Temporal workflow: pure, deterministic orchestration.
No LLM calls, no clock, no randomness, no I/O — every side effect is an
activity. This is the LangGraph control flow (graph.py) lifted into Temporal.

Exposes a `snapshot` query so a UI can read live progress (phase + per-room
completion) and the draft plans while the workflow is parked for approval."""

import asyncio
import re
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.activities import (
        AgentTurnInput, AgentTurnResult, ToolInput, ToolResult,
        ExtractRoomsInput, RoomPlanInput, RoomPlan, ShoppingListInput,
        agent_turn, run_tool, extract_rooms, plan_room, build_shopping_list,
    )

MAX_TOOL_LOOPS = 3
RETRY = RetryPolicy(initial_interval=timedelta(seconds=1),
                    backoff_coefficient=2.0, maximum_attempts=3)
ACT_TIMEOUT = timedelta(seconds=90)

_PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn":   re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}


def _guard(message: str, max_len: int) -> tuple[bool, str, dict]:
    """Deterministic input guard — pure function of (message, max_len), so it's
    safe to run inline in the workflow. Mirrors app/nodes/input_guard.py:
    detects PII but does NOT block on it."""
    if message is None:
        return (False,
                "I didn't receive a message. Could you share what you'd like help with?",
                {"input_guard": {"rejected": True, "reason": "no_user_message"}})
    if not message.strip():
        return (False,
                "Your message looks empty. Tell me a bit about what you're working on and I'll help.",
                {"input_guard": {"rejected": True, "reason": "empty_message"}})
    if len(message) > max_len:
        return (False,
                f"Your message is a bit long for me to process well "
                f"({len(message)} chars, max {max_len}). Could you trim it down to the core question?",
                {"input_guard": {"rejected": True, "reason": "too_long"}})
    pii = [n for n, p in _PII_PATTERNS.items() if p.search(message)]
    meta = {"input_guard": {"rejected": False, "length": len(message)}}
    if pii:
        meta["input_guard"]["pii_types"] = pii
    return (True, "", meta)


def _is_whole_home(message: str) -> bool:
    m = message.lower()
    return any(kw in m for kw in
               ("whole apartment", "whole home", "entire apartment",
                "entire home", "whole house", "every room", "all the rooms"))


@workflow.defn
class DecorAgentWorkflow:
    def __init__(self) -> None:
        # signal state
        self._decision: str | None = None        # "approve" | "reject"
        self._new_budget: str | None = None
        # live-status state (read via the snapshot query)
        self._phase: str = "starting"
        self._rooms_total: int = 0
        self._rooms_done: list[str] = []
        self._draft_plans: list[dict] = []        # plain dicts, query-serializable
        self._budget: str = "not specified"

    # ---------- Signals: human-in-the-loop ----------
    @workflow.signal
    def approve(self) -> None:
        self._decision = "approve"

    @workflow.signal
    def reject(self) -> None:
        self._decision = "reject"

    @workflow.signal
    def tweak_budget(self, new_budget: str) -> None:
        self._new_budget = new_budget

    # ---------- Queries: read running state without disturbing it ----------
    @workflow.query
    def snapshot(self) -> dict:
        """Live progress + draft, for the UI status panel. Read-only, returns
        plain serializable data."""
        return {
            "phase": self._phase,
            "rooms_total": self._rooms_total,
            "rooms_done": list(self._rooms_done),
            "draft_plans": list(self._draft_plans),
            "budget": self._budget,
            "decision": self._decision,
        }

    # ---------- Main ----------
    @workflow.run
    async def run(self, message: str, budget: str = "not specified",
                  context_key: str = "anonymous",
                  max_input_length: int = 2000) -> dict:
        self._budget = budget
        self._phase = "validating"
        metadata = {"routed_to": None, "tool_calls_made": 0,
                    "input_tokens": 0, "output_tokens": 0,
                    "rooms_planned": [], "models_used": []}

        valid, reject_msg, guard_meta = _guard(message, max_input_length)
        metadata.update(guard_meta)
        if not valid:
            self._phase = "rejected"
            return {"response": reject_msg,
                    "metadata": {**metadata, "routed_to": "input_guard_reject"}}

        if _is_whole_home(message):
            return await self._plan_whole_home(message, budget, context_key, metadata)

        # ----- Standard single-turn agent loop -----
        self._phase = "thinking"
        messages = [{"role": "user", "content": message}]
        for _ in range(MAX_TOOL_LOOPS):
            turn: AgentTurnResult = await workflow.execute_activity(
                agent_turn,
                AgentTurnInput(messages=messages, context_key=context_key),
                start_to_close_timeout=ACT_TIMEOUT, retry_policy=RETRY)
            metadata["input_tokens"] += turn.input_tokens
            metadata["output_tokens"] += turn.output_tokens
            metadata["models_used"].append(turn.model)

            if not turn.tool_calls:
                self._phase = "completed"
                return {"response": turn.text,
                        "metadata": {**metadata,
                                     "routed_to": metadata["routed_to"] or "direct"}}

            for tc in turn.tool_calls:
                metadata["routed_to"] = metadata["routed_to"] or tc["name"]
                metadata["tool_calls_made"] += 1
                res: ToolResult = await workflow.execute_activity(
                    run_tool,
                    ToolInput(name=tc["name"], args=tc["args"], context_key=context_key),
                    start_to_close_timeout=ACT_TIMEOUT, retry_policy=RETRY)
                metadata["models_used"].append(res.model_used)
                messages.append({"role": "assistant", "content": turn.text,
                                 "tool_calls": turn.tool_calls})
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": res.text})

        self._phase = "completed"
        return {"response": "I had trouble completing that — could you rephrase?",
                "metadata": {**metadata, "routed_to": "loop_exhausted"}}

    # ---------- Whole-home: fan-out → human approval → shopping list ----------
    async def _plan_one(self, room: str, budget: str, context_key: str) -> RoomPlan:
        """Wrap a single room activity so we can mark it done the moment it
        returns — this is what makes per-room progress 'live' for the query.
        Still deterministic: Temporal records each completion in history."""
        result: RoomPlan = await workflow.execute_activity(
            plan_room,
            RoomPlanInput(room=room, budget=budget, context_key=context_key),
            start_to_close_timeout=ACT_TIMEOUT, retry_policy=RETRY)
        self._rooms_done.append(result.room)
        return result

    async def _plan_whole_home(self, message: str, budget: str,
                               context_key: str, metadata: dict) -> dict:
        self._phase = "extracting_rooms"
        rooms = (await workflow.execute_activity(
            extract_rooms,
            ExtractRoomsInput(message=message, context_key=context_key),
            start_to_close_timeout=ACT_TIMEOUT, retry_policy=RETRY)).rooms

        while True:
            # FAN-OUT with incremental progress. Each room marks itself done as
            # it completes, so the snapshot query shows "2 of 3" mid-flight.
            self._phase = "fanning_out"
            self._rooms_total = len(rooms)
            self._rooms_done = []
            self._budget = budget
            tasks = [
                asyncio.create_task(self._plan_one(r, budget, context_key))
                for r in rooms
            ]
            plans: list[RoomPlan] = await asyncio.gather(*tasks)

            metadata["rooms_planned"] = [p.room for p in plans]
            metadata["models_used"].extend(p.model_used for p in plans)

            # publish the draft for the query, then park for the human
            self._draft_plans = [{"room": p.room, "plan_text": p.plan_text}
                                 for p in plans]
            self._phase = "awaiting_decision"

            # Do NOT reset _decision/_new_budget here: a signal can arrive before
            # we reach this point (e.g. while rooms are still being planned), and
            # clearing it would discard the human's decision and park forever.
            # We consume the budget tweak explicitly after using it instead.
            await workflow.wait_condition(
                lambda: self._decision is not None or self._new_budget is not None)

            if self._new_budget is not None:
                budget = self._new_budget
                self._new_budget = None           # consume, then re-plan
                continue                          # re-plan with new budget
            if self._decision == "reject":
                self._phase = "rejected"
                return {"response": "Plan discarded. Start over whenever you like.",
                        "metadata": {**metadata, "routed_to": "rejected"}}
            break                                 # approved

        self._phase = "building_list"
        shopping = await workflow.execute_activity(
            build_shopping_list,
            ShoppingListInput(
                approved_plans=self._draft_plans, budget=budget,
                context_key=context_key),
            start_to_close_timeout=ACT_TIMEOUT, retry_policy=RETRY)

        self._phase = "completed"
        plan_text = "\n\n".join(f"## {p.room}\n{p.plan_text}" for p in plans)
        return {"response": f"{plan_text}\n\n# Shopping List\n{shopping}",
                "metadata": {**metadata, "routed_to": "whole_home_approved"}}
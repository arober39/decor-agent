"""Temporal workflow tests using the time-skipping test environment.
Activities are mocked so tests run offline, deterministically, and instantly."""

import uuid
import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import app.activities as acts
from app.workflow import DecorAgentWorkflow

TASK_QUEUE = "test-decor"


# --- Mocked activities (registered under the same names the workflow calls) ---

@activity.defn(name="agent_turn")
async def mock_agent_turn(inp: acts.AgentTurnInput) -> acts.AgentTurnResult:
    return acts.AgentTurnResult(
        text="Walnut floors pair beautifully with sage green walls.",
        tool_calls=[], input_tokens=10, output_tokens=20, model="mock-model")

@activity.defn(name="run_tool")
async def mock_run_tool(inp: acts.ToolInput) -> acts.ToolResult:
    return acts.ToolResult(text=f"advice from {inp.name}", latency_ms=1.0,
                           model_used="mock-model")

@activity.defn(name="extract_rooms")
async def mock_extract_rooms(inp: acts.ExtractRoomsInput) -> acts.ExtractRoomsResult:
    return acts.ExtractRoomsResult(rooms=["living room", "bedroom"])

@activity.defn(name="plan_room")
async def mock_plan_room(inp: acts.RoomPlanInput) -> acts.RoomPlan:
    return acts.RoomPlan(room=inp.room, plan_text=f"plan for {inp.room} @ {inp.budget}",
                         latency_ms=1.0, model_used="mock-model")

@activity.defn(name="build_shopping_list")
async def mock_build_shopping_list(inp: acts.ShoppingListInput) -> str:
    return "1x 72-inch sofa, 2x table lamps, 1x 8x10 rug"


MOCKS = [mock_agent_turn, mock_run_tool, mock_extract_rooms,
         mock_plan_room, mock_build_shopping_list]


def _wf_id() -> str:
    return f"test-{uuid.uuid4()}"


@pytest.mark.asyncio
async def test_direct_answer():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[DecorAgentWorkflow], activities=MOCKS):
            result = await env.client.execute_workflow(
                DecorAgentWorkflow.run,
                args=["what goes with walnut floors?", "not specified", "test", 2000],
                id=_wf_id(), task_queue=TASK_QUEUE)
            assert "sage green" in result["response"]
            assert result["metadata"]["routed_to"] == "direct"


@pytest.mark.asyncio
async def test_input_guard_rejects_empty():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[DecorAgentWorkflow], activities=MOCKS):
            result = await env.client.execute_workflow(
                DecorAgentWorkflow.run,
                args=["   ", "not specified", "test", 2000],
                id=_wf_id(), task_queue=TASK_QUEUE)
            assert result["metadata"]["routed_to"] == "input_guard_reject"
            assert result["metadata"]["input_guard"]["reason"] == "empty_message"


@pytest.mark.asyncio
async def test_input_guard_rejects_too_long():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[DecorAgentWorkflow], activities=MOCKS):
            result = await env.client.execute_workflow(
                DecorAgentWorkflow.run,
                args=["a" * 3000, "not specified", "test", 2000],
                id=_wf_id(), task_queue=TASK_QUEUE)
            assert result["metadata"]["input_guard"]["reason"] == "too_long"


@pytest.mark.asyncio
async def test_human_in_the_loop_approve():
    """Fan-out → durable wait → approve signal → shopping list.
    Time-skipping fast-forwards the durable wait so this runs instantly."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[DecorAgentWorkflow], activities=MOCKS):
            handle = await env.client.start_workflow(
                DecorAgentWorkflow.run,
                args=["plan my whole apartment", "$8000", "test", 2000],
                id=_wf_id(), task_queue=TASK_QUEUE)
            await handle.signal(DecorAgentWorkflow.approve)
            result = await handle.result()
            assert "Shopping List" in result["response"]
            assert result["metadata"]["routed_to"] == "whole_home_approved"
            assert result["metadata"]["rooms_planned"] == ["living room", "bedroom"]


@pytest.mark.asyncio
async def test_human_in_the_loop_tweak_then_approve():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[DecorAgentWorkflow], activities=MOCKS):
            handle = await env.client.start_workflow(
                DecorAgentWorkflow.run,
                args=["plan my whole apartment", "$8000", "test", 2000],
                id=_wf_id(), task_queue=TASK_QUEUE)
            await handle.signal(DecorAgentWorkflow.tweak_budget, "$5000")
            await handle.signal(DecorAgentWorkflow.approve)
            result = await handle.result()
            assert result["metadata"]["routed_to"] == "whole_home_approved"


@pytest.mark.asyncio
async def test_human_in_the_loop_reject():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[DecorAgentWorkflow], activities=MOCKS):
            handle = await env.client.start_workflow(
                DecorAgentWorkflow.run,
                args=["plan my whole apartment", "$8000", "test", 2000],
                id=_wf_id(), task_queue=TASK_QUEUE)
            await handle.signal(DecorAgentWorkflow.reject)
            result = await handle.result()
            assert result["metadata"]["routed_to"] == "rejected"
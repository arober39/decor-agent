"""Temporal worker: hosts the workflow and activities, polls the task queue.
Run this in its own process alongside the Temporal dev server."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

from temporalio.client import Client
from temporalio.worker import Worker

from app.activities import (
    agent_turn, run_tool, extract_rooms, plan_room, build_shopping_list,
)
from app.logging import configure_logging, get_logger
from app.workflow import DecorAgentWorkflow

TASK_QUEUE = "decor-agent"
log = get_logger(__name__)


async def main() -> None:
    configure_logging()
    # Initialize LaunchDarkly so activities resolve AI Configs (no-op if offline).
    try:
        from app.flags import init_client
        init_client()
    except ImportError:
        pass

    client = await Client.connect("localhost:7233")
    log.info("worker.starting", task_queue=TASK_QUEUE)
    # Sync (blocking) activities need an executor; max_workers caps how many
    # activities run concurrently — large enough to cover the per-room fan-out.
    with ThreadPoolExecutor(max_workers=10) as activity_executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[DecorAgentWorkflow],
            activities=[agent_turn, run_tool, extract_rooms, plan_room,
                        build_shopping_list],
            activity_executor=activity_executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import get_settings
from app.flags import build_context, get_flag, set_current_user_tier
from app.graph import run_agent
from app.logging import configure_logging, get_logger

VERSION = "1.0.0"

# Must match app/worker.py TASK_QUEUE so the worker picks up these workflows.
TEMPORAL_TASK_QUEUE = "decor-agent"

log = get_logger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context_key: str | None = None
    user_tier: Literal["free", "premium"] | None = None


class ChatResponse(BaseModel):
    response: str
    metadata: dict
    message_id: str
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    version: str

class PlanRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    budget: str = "not specified"
    context_key: str | None = None


class PlanStarted(BaseModel):
    workflow_id: str
    status: str


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "tweak_budget"]
    new_budget: str | None = None

async def _temporal_client():
    """Lazy import + connect so the app still boots if Temporal isn't running."""
    from temporalio.client import Client
    return await Client.connect("localhost:7233")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Initialize LaunchDarkly clients so runtime flag checks use live values.
    try:
        from app.flags import init_client

        init_client()
    except ImportError:
        pass
    log.info("server.started", version=VERSION)
    try:
        yield
    finally:
        # Clean up LaunchDarkly client if initialized. flags.py isn't wired
        # up yet; this guard keeps the shutdown path quiet until it is.
        try:
            from app import flags
            close = getattr(flags, "close_client", None)
            if callable(close):
                close()
        except ImportError:
            pass
        log.info("server.stopped")


app = FastAPI(title="Decor Agent", version=VERSION, lifespan=lifespan)
BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        log.exception(
            "http.unhandled_exception",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            duration_ms=round(duration_ms, 2),
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    log.info(
        "http.request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=status,
        duration_ms=round(duration_ms, 2),
    )
    response.headers["x-request-id"] = request_id
    return response


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=VERSION)


@app.get("/")
async def frontend() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")

@app.get("/temporal")
async def temporal_page() -> FileResponse:
    return FileResponse(WEB_DIR / "temporal.html")

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> JSONResponse:
    message_id = str(uuid.uuid4())
    context_key = req.context_key or f"anon-{uuid.uuid4()}"
    timestamp = datetime.now(timezone.utc).isoformat()
    set_current_user_tier(req.user_tier)
    context = build_context(context_key)

    log.info(
        "chat.request",
        message_id=message_id,
        context_key=context_key,
        user_tier=req.user_tier,
        message_len=len(req.message),
    )

    if not get_flag("decor-agent-enabled", context, default=True):
        log.info(
            "chat.maintenance_mode",
            message_id=message_id,
            context_key=context_key,
            flag_key="decor-agent-enabled",
        )
        body = ChatResponse(
            response="Decor Agent is temporarily unavailable for maintenance. Check back soon!",
            metadata={"routed_to": "maintenance"},
            message_id=message_id,
            timestamp=timestamp,
        )
        return JSONResponse(status_code=200, content=body.model_dump())

    try:
        result = run_agent(req.message, context_key=context_key)
    except Exception as exc:
        log.error(
            "chat.error",
            message_id=message_id,
            context_key=context_key,
            error=str(exc),
            error_type=exc.__class__.__name__,
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Something went wrong processing your message. Please try again.",
                "message_id": message_id,
            },
        )

    body = ChatResponse(
        response=result["response"],
        metadata=result["metadata"],
        message_id=message_id,
        timestamp=timestamp,
    )
    log.info(
        "chat.response",
        message_id=message_id,
        context_key=context_key,
        routed_to=result["metadata"].get("routed_to"),
        response_len=len(result["response"]),
    )
    return JSONResponse(status_code=200, content=body.model_dump())

# ----------------------- AFTER: Temporal-backed endpoints -----------------------

@app.post("/api/temporal/chat", response_model=ChatResponse)
async def temporal_chat(req: ChatRequest) -> JSONResponse:
    """Single-turn chat, run as a Temporal workflow (durable, retried)."""
    message_id = str(uuid.uuid4())
    context_key = req.context_key or f"anon-{uuid.uuid4()}"
    timestamp = datetime.now(timezone.utc).isoformat()
    settings = get_settings()  # config resolved HERE, in the caller, then passed in

    try:
        client = await _temporal_client()
        from app.workflow import DecorAgentWorkflow
        result = await client.execute_workflow(
            DecorAgentWorkflow.run,
            args=[req.message, "not specified", context_key, settings.max_input_length],
            id=f"decor-chat-{message_id}",
            task_queue=TEMPORAL_TASK_QUEUE,
        )
    except Exception as exc:
        log.error("temporal_chat.error", error=str(exc), traceback=traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": "Workflow failed. Is the Temporal worker running?",
                     "message_id": message_id},
        )

    body = ChatResponse(response=result["response"], metadata=result["metadata"],
                        message_id=message_id, timestamp=timestamp)
    return JSONResponse(status_code=200, content=body.model_dump())


@app.post("/api/temporal/plan", response_model=PlanStarted)
async def temporal_plan(req: PlanRequest) -> JSONResponse:
    """Start a whole-home plan workflow. Returns a workflow_id you then
    send approve/reject/tweak_budget signals to."""
    context_key = req.context_key or f"anon-{uuid.uuid4()}"
    workflow_id = f"decor-plan-{uuid.uuid4()}"
    settings = get_settings()

    try:
        client = await _temporal_client()
        from app.workflow import DecorAgentWorkflow
        await client.start_workflow(
            DecorAgentWorkflow.run,
            args=[req.message, req.budget, context_key, settings.max_input_length],
            id=workflow_id,
            task_queue=TEMPORAL_TASK_QUEUE,
        )
    except Exception as exc:
        log.error("temporal_plan.error", error=str(exc), traceback=traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": "Could not start workflow. Is the Temporal worker running?"},
        )

    return JSONResponse(status_code=200,
                        content=PlanStarted(workflow_id=workflow_id, status="running").model_dump())


@app.post("/api/temporal/plan/{workflow_id}/decision")
async def temporal_plan_decision(workflow_id: str, req: DecisionRequest) -> JSONResponse:
    """Send the human-in-the-loop signal to a running plan workflow."""
    try:
        client = await _temporal_client()
        from app.workflow import DecorAgentWorkflow
        handle = client.get_workflow_handle(workflow_id)
        if req.decision == "approve":
            await handle.signal(DecorAgentWorkflow.approve)
        elif req.decision == "reject":
            await handle.signal(DecorAgentWorkflow.reject)
        elif req.decision == "tweak_budget":
            await handle.signal(DecorAgentWorkflow.tweak_budget, req.new_budget or "not specified")
    except Exception as exc:
        log.error("temporal_decision.error", error=str(exc))
        return JSONResponse(status_code=500, content={"detail": "Could not signal workflow."})

    return JSONResponse(status_code=200, content={"workflow_id": workflow_id, "signal": req.decision})


@app.get("/api/temporal/plan/{workflow_id}/result")
async def temporal_plan_result(workflow_id: str) -> JSONResponse:
    """Block until the workflow completes and return its result.
    (For a demo; in production you'd poll or use the query instead.)"""
    try:
        client = await _temporal_client()
        handle = client.get_workflow_handle(workflow_id)
        result = await handle.result()
    except Exception as exc:
        log.error("temporal_result.error", error=str(exc))
        return JSONResponse(status_code=500, content={"detail": "Could not fetch result."})
    return JSONResponse(status_code=200, content=result)

@app.get("/api/temporal/plan/{workflow_id}/snapshot")
async def temporal_plan_snapshot(workflow_id: str) -> JSONResponse:
    """Read live workflow progress (phase, per-room completion, draft plans)
    via the workflow's snapshot query — works while the workflow is parked."""
    try:
        client = await _temporal_client()
        from app.workflow import DecorAgentWorkflow
        handle = client.get_workflow_handle(workflow_id)
        snap = await handle.query(DecorAgentWorkflow.snapshot)
    except Exception as exc:
        log.error("temporal_snapshot.error", error=str(exc))
        return JSONResponse(status_code=500, content={"detail": "Could not query workflow."})
    return JSONResponse(status_code=200, content=snap)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)

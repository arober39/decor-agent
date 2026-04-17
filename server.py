import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.graph import run_agent
from app.logging import configure_logging, get_logger

VERSION = "1.0.0"

log = get_logger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context_key: str | None = None


class ChatResponse(BaseModel):
    response: str
    metadata: dict
    message_id: str
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
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


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> JSONResponse:
    message_id = str(uuid.uuid4())
    context_key = req.context_key or f"anon-{uuid.uuid4()}"
    timestamp = datetime.now(timezone.utc).isoformat()

    log.info(
        "chat.request",
        message_id=message_id,
        context_key=context_key,
        message_len=len(req.message),
    )

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)

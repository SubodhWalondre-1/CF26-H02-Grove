import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from app.api.routes import router as api_router
from app.api.pharmacy_routes import router as pharmacy_router
from app.api.diagnostics_routes import router as diagnostics_router
from app.api.transfer_routes import router as transfer_router
from app.api.escalation_routes import router as escalation_router
from app.api.override_routes import router as override_router
from app.api.readiness_routes import router as readiness_router
from app.api.recommendation_routes import router as recommendation_router
from app.api.records_routes import router as records_router
from app.api.public_board_routes import router as public_board_router
from app.api.admin_alerts_routes import router as admin_alerts_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, init_redis
from app.core.scheduler import start_scheduler, stop_scheduler
from app.realtime.websocket import redis_listener, router as websocket_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifecycle event handler for application startup and graceful shutdown.
    """
    # Startup sequence
    setup_logging()
    logger.info("Initializing database connection...")
    await init_db()

    logger.info("Initializing Redis connection...")
    await init_redis()

    # a. Start Redis -> WebSocket fan-out background task
    app.state.redis_listener_task = asyncio.create_task(redis_listener())
    logger.info("WebSocket Redis listener task started")

    # b. Start APScheduler TTL engine
    await start_scheduler()

    # c. Trigger crash-recovery scan, if enabled
    if settings.recovery_scan_on_startup:
        try:
            from app.workers.tasks import run_crash_recovery_scan_task

            run_crash_recovery_scan_task.delay(triggered_by="startup")
            logger.info("Crash-recovery scan dispatched to Celery worker")
        except Exception:
            logger.exception(
                "Failed to dispatch startup crash-recovery scan — is the celery "
                "broker (Redis) reachable and a celery_worker container running? "
                "The app will still start; incomplete transactions can be resolved "
                "manually via POST /recovery/{tx_id}/resolve in the meantime."
            )

    logger.info("Mediora Phase 4 startup complete — TTL engine + realtime layer live")
    yield

    # Shutdown sequence
    # a. Cancel WebSocket fan-out task cleanly
    if hasattr(app.state, "redis_listener_task"):
        app.state.redis_listener_task.cancel()
        try:
            await app.state.redis_listener_task
        except asyncio.CancelledError:
            pass

    # b. Stop the scheduler
    await stop_scheduler()

    logger.info("Closing Redis connection...")
    await close_redis()
    logger.info("Mediora shutdown complete.")


app = FastAPI(
    title="Mediora — Clinical Resource Transaction Coordinator",
    description="Coordinates concurrent access to clinical resources with atomicity, fairness, and recoverability guarantees (Phase 4: TTL Enforcement, Crash Recovery & Real-time WebSockets live).",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware configuration
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code", f"http_{exc.status_code}")
        message = exc.detail.get("message", str(exc.detail))
        tx_id = exc.detail.get("tx_id", None)
    else:
        code = f"http_{exc.status_code}"
        message = str(exc.detail)
        tx_id = None

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "tx_id": tx_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception(f"Unhandled server error: {exc}", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "internal_server_error",
                "message": (
                    "An unexpected error occurred. Please try again later."
                ),
                "tx_id": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        },
    )


# Include API and WebSocket routes
app.include_router(api_router)
app.include_router(pharmacy_router)
app.include_router(diagnostics_router)
app.include_router(transfer_router)
app.include_router(escalation_router)
app.include_router(override_router)
app.include_router(readiness_router)
app.include_router(recommendation_router)
app.include_router(records_router)
app.include_router(public_board_router)
app.include_router(admin_alerts_router)
app.include_router(websocket_router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.app_env == "development"),
    )


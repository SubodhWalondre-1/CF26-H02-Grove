import asyncio
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.models import User

logger = get_logger(__name__)

router = APIRouter()


class ConnectionManager:
    """
    Manages active dashboard WebSocket connections and fans out live messages.
    """
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)


manager = ConnectionManager()


async def redis_listener() -> None:
    """
    Background subscriber task running on FastAPI lifespan.
    Subscribes to 'pubsub:dashboard' and forwards every incoming message to active WebSocket clients.
    """
    redis_client = await get_redis()
    if not redis_client:
        logger.warning("Redis client unavailable; WebSocket Redis listener cannot start.")
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("pubsub:dashboard")
    logger.info("WebSocket Redis listener subscribed to 'pubsub:dashboard'")

    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                data = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            await manager.broadcast(data)
    except asyncio.CancelledError:
        await pubsub.unsubscribe("pubsub:dashboard")
        raise
    except Exception:
        logger.exception("redis_listener crashed — WS clients will stop receiving updates")


@router.websocket("/ws/dashboard")
async def dashboard_ws(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Live real-time dashboard WebSocket stream.
    Authenticates via JWT token query parameter and broadcasts system-wide state transitions.
    """
    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=1008)
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=1008)
        return

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)
    logger.info(f"WS dashboard client connected: user={user.user_id}")

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
        logger.info(f"WS dashboard client disconnected: user={user.user_id}")


# =============================================================================
# BED REALTIME BROADCASTER & WEBSOCKET ENDPOINT
# =============================================================================

async def bed_updates_broadcaster(
    websocket: WebSocket,
    redis_client: Optional[aioredis.Redis],
) -> None:
    """
    Subscribes to Redis 'bed_updates' and 'shortage_alerts' channels.
    Forwards every bed status change and shortage alert to connected dashboard clients.
    """
    if not redis_client:
        await websocket.accept()
        logger.warning("Redis unavailable for bed_updates_broadcaster")
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("bed_updates", "shortage_alerts")

    try:
        await websocket.accept()
        async for message in pubsub.listen():
            if message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                except (json.JSONDecodeError, TypeError):
                    continue
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.warning(f"Error in bed_updates_broadcaster: {e}")
    finally:
        try:
            await pubsub.unsubscribe("bed_updates", "shortage_alerts")
            await pubsub.close()
        except Exception:
            pass


@router.websocket("/ws/beds")
async def bed_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="Optional JWT access token"),
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[aioredis.Redis] = Depends(get_redis),
) -> None:
    """
    Real-time Bed status and shortage alert WebSocket stream.
    Subscribes to 'bed_updates' and 'shortage_alerts' Redis channels.
    """
    if token:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if user_id:
                user = await db.get(User, user_id)
                if user is None or not user.is_active:
                    await websocket.close(code=1008)
                    return
        except Exception:
            await websocket.close(code=1008)
            return

    await bed_updates_broadcaster(websocket, redis_client)


# =============================================================================
# PHARMACY REALTIME WEBSOCKET ENDPOINT
# =============================================================================

async def pharmacy_updates_broadcaster(
    websocket: WebSocket,
    redis_client: Optional[aioredis.Redis],
) -> None:
    """
    Subscribes to Redis 'pharmacy_alerts' channel.
    Forwards every pharmacy stock change and shortage alert to connected clients.
    """
    if not redis_client:
        await websocket.accept()
        logger.warning("Redis unavailable for pharmacy_updates_broadcaster")
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("pharmacy_alerts")

    try:
        await websocket.accept()
        async for message in pubsub.listen():
            if message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                except (json.JSONDecodeError, TypeError):
                    continue
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.warning(f"Error in pharmacy_updates_broadcaster: {e}")
    finally:
        try:
            await pubsub.unsubscribe("pharmacy_alerts")
            await pubsub.close()
        except Exception:
            pass


@router.websocket("/ws/pharmacy")
async def pharmacy_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="Optional JWT access token"),
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[aioredis.Redis] = Depends(get_redis),
) -> None:
    """
    Real-time Pharmacy stock and shortage alert WebSocket stream.
    Subscribes to 'pharmacy_alerts' Redis channel.
    """
    if token:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if user_id:
                user = await db.get(User, user_id)
                if user is None or not user.is_active:
                    await websocket.close(code=1008)
                    return
        except Exception:
            await websocket.close(code=1008)
            return

    await pharmacy_updates_broadcaster(websocket, redis_client)


# =============================================================================
# DIAGNOSTICS & LAB REALTIME WEBSOCKET ENDPOINT
# =============================================================================

async def diagnostics_updates_broadcaster(
    websocket: WebSocket,
    redis_client: Optional[aioredis.Redis],
) -> None:
    """
    Subscribes to Redis 'diagnostics_updates' channel.
    Forwards every equipment schedule change and lab sample state update to connected clients.
    """
    if not redis_client:
        await websocket.accept()
        logger.warning("Redis unavailable for diagnostics_updates_broadcaster")
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("diagnostics_updates")

    try:
        await websocket.accept()
        async for message in pubsub.listen():
            if message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                except (json.JSONDecodeError, TypeError):
                    continue
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.warning(f"Error in diagnostics_updates_broadcaster: {e}")
    finally:
        try:
            await pubsub.unsubscribe("diagnostics_updates")
            await pubsub.close()
        except Exception:
            pass


@router.websocket("/ws/diagnostics")
async def diagnostics_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="Optional JWT access token"),
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[aioredis.Redis] = Depends(get_redis),
) -> None:
    """
    Real-time Diagnostics and Lab status WebSocket stream.
    Subscribes to 'diagnostics_updates' Redis channel.
    """
    if token:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if user_id:
                user = await db.get(User, user_id)
                if user is None or not user.is_active:
                    await websocket.close(code=1008)
                    return
        except Exception:
            await websocket.close(code=1008)
            return

    await diagnostics_updates_broadcaster(websocket, redis_client)


# =============================================================================
# PATIENT TRANSFER REALTIME WEBSOCKET ENDPOINT
# =============================================================================

async def transfer_updates_broadcaster(
    websocket: WebSocket,
    redis_client: Optional[aioredis.Redis],
) -> None:
    """
    Subscribes to Redis 'transfer_updates' channel.
    Forwards in-flight transfer state transitions to connected clients.
    """
    if not redis_client:
        await websocket.accept()
        logger.warning("Redis unavailable for transfer_updates_broadcaster")
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("transfer_updates")

    try:
        await websocket.accept()
        async for message in pubsub.listen():
            if message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                except (json.JSONDecodeError, TypeError):
                    continue
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.warning(f"Error in transfer_updates_broadcaster: {e}")
    finally:
        try:
            await pubsub.unsubscribe("transfer_updates")
            await pubsub.close()
        except Exception:
            pass


@router.websocket("/ws/transfers")
async def transfers_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="Optional JWT access token"),
    db: AsyncSession = Depends(get_db),
    redis_client: Optional[aioredis.Redis] = Depends(get_redis),
) -> None:
    """
    Real-time Patient Transfer status WebSocket stream.
    Subscribes to 'transfer_updates' Redis channel.
    """
    if token:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if user_id:
                user = await db.get(User, user_id)
                if user is None or not user.is_active:
                    await websocket.close(code=1008)
                    return
        except Exception:
            await websocket.close(code=1008)
            return

    await transfer_updates_broadcaster(websocket, redis_client)


# =============================================================================
# PUBLIC SHORTAGE ALERTS WEBSOCKET ENDPOINT (UNAUTHENTICATED)
# =============================================================================

async def public_alerts_broadcaster(
    websocket: WebSocket,
    redis_client: Optional[aioredis.Redis],
) -> None:
    """
    Subscribes to Redis 'pubsub:public_alerts' channel.
    Unauthenticated broadcaster streaming live shortage alerts and resolution events
    directly to public lobby kiosks and donation dashboards.
    """
    if not redis_client:
        await websocket.accept()
        logger.warning("Redis unavailable for public_alerts_broadcaster")
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("pubsub:public_alerts")

    try:
        await websocket.accept()
        async for message in pubsub.listen():
            if message.get("type") == "message":
                try:
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                except (json.JSONDecodeError, TypeError):
                    continue
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.warning(f"Error in public_alerts_broadcaster: {e}")
    finally:
        try:
            await pubsub.unsubscribe("pubsub:public_alerts")
            await pubsub.close()
        except Exception:
            pass


@router.websocket("/ws/public-alerts")
async def public_alerts_ws(
    websocket: WebSocket,
    redis_client: Optional[aioredis.Redis] = Depends(get_redis),
) -> None:
    """
    Unauthenticated Public Shortage Alerts WebSocket stream.
    Zero PHI, designed for lobby TV screens and donation kiosk displays.
    """
    await public_alerts_broadcaster(websocket, redis_client)


import json
import logging
from typing import Any, Dict, Optional
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level client singleton
redis_client: Optional[aioredis.Redis] = None


async def init_redis() -> Optional[aioredis.Redis]:
    """
    Initializes async Redis client, tests connection with PING,
    and handles connection errors gracefully.
    """
    global redis_client
    try:
        client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        await client.ping()
        redis_client = client
        logger.info("Successfully connected to Redis instance.")
        return redis_client
    except (ConnectionError, RedisError, Exception) as e:
        logger.warning(
            f"Failed to connect to Redis at {settings.redis_url}: {e}. "
            "Realtime pub/sub notifications may be degraded."
        )
        redis_client = None
        return None


async def close_redis() -> None:
    """
    Gracefully closes active Redis connection.
    """
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
            logger.info("Redis connection closed gracefully.")
        except Exception as e:
            logger.error(f"Error while closing Redis connection: {e}")
        finally:
            redis_client = None


async def get_redis() -> Optional[aioredis.Redis]:
    """
    FastAPI dependency providing the shared Redis client.
    """
    return redis_client


async def publish_event(
    channel: str = "pubsub:dashboard",
    event_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Serializes event data to JSON and publishes to the designated Redis channel.
    Fails gracefully if Redis is unavailable.
    """
    if event_data is None:
        event_data = {}

    if not redis_client:
        logger.warning(
            f"Redis client not initialized. Skipped publishing to channel '{channel}'."
        )
        return False

    try:
        payload = json.dumps(event_data, default=str)
        await redis_client.publish(channel, payload)
        return True
    except (ConnectionError, RedisError, Exception) as e:
        logger.error(f"Failed to publish event to Redis channel '{channel}': {e}")
        return False


async def set_hold_ttl(
    tx_id: str,
    seconds: int,
    hold_expires_at_iso: str,
) -> None:
    """
    Sets non-authoritative hold TTL cache key hold:ttl:{tx_id} with expiration in seconds.
    """
    if not redis_client:
        return
    try:
        await redis_client.setex(f"hold:ttl:{tx_id}", seconds, hold_expires_at_iso)
    except (ConnectionError, RedisError, Exception) as e:
        logger.warning(f"Failed to set hold TTL in Redis for TX {tx_id}: {e}")


async def clear_hold_ttl(tx_id: str) -> None:
    """
    Deletes hold:ttl:{tx_id} key from Redis.
    """
    if not redis_client:
        return
    try:
        await redis_client.delete(f"hold:ttl:{tx_id}")
    except (ConnectionError, RedisError, Exception) as e:
        logger.warning(f"Failed to clear hold TTL in Redis for TX {tx_id}: {e}")


async def mark_ttl_warned(
    tx_id: str,
    ttl_seconds: int,
) -> bool:
    """
    Atomically sets ttl:warned:{tx_id} = "1" with expiration ttl_seconds if not exists (NX).
    Returns True if key was newly set (warning not yet sent), False if key existed (already warned).
    Fails open (returns True) on connection error.
    """
    if not redis_client:
        return True
    try:
        res = await redis_client.set(
            f"ttl:warned:{tx_id}", "1", nx=True, ex=ttl_seconds
        )
        return bool(res)
    except (ConnectionError, RedisError, Exception) as e:
        logger.warning(f"Failed to mark TTL warned in Redis for TX {tx_id}: {e}")
        return True


async def clear_ttl_warned(tx_id: str) -> None:
    """
    Deletes ttl:warned:{tx_id} key from Redis.
    """
    if not redis_client:
        return
    try:
        await redis_client.delete(f"ttl:warned:{tx_id}")
    except (ConnectionError, RedisError, Exception) as e:
        logger.warning(f"Failed to clear TTL warned in Redis for TX {tx_id}: {e}")


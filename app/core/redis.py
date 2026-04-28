import redis.asyncio as redis

from app.core.config import settings

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)


async def get_redis() -> redis.Redis:
    """Dependency that provides a Redis client."""
    return redis_client


async def check_rate_limit(user_id: str, limit: int) -> bool:
    """Check if user has exceeded daily horoscope generation limit.

    Returns True if the user is within the limit, False if exceeded.
    """
    key = f"rate_limit:horoscope:{user_id}"
    current = await redis_client.get(key)

    if current is None:
        await redis_client.setex(key, 86400, 1)  # 24 hours TTL
        return True

    if int(current) >= limit:
        return False

    await redis_client.incr(key)
    return True


async def get_cached_horoscope(user_id: str, date: str) -> str | None:
    """Get cached horoscope for a user and date."""
    key = f"horoscope:{user_id}:{date}"
    return await redis_client.get(key)


async def cache_horoscope(user_id: str, date: str, text: str, ttl: int = 86400) -> None:
    """Cache a generated horoscope."""
    key = f"horoscope:{user_id}:{date}"
    await redis_client.setex(key, ttl, text)

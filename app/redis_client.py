import redis

_client: redis.Redis | None = None


def init_redis(app) -> None:
    global _client
    url = app.config.get("REDIS_URL")
    if url:
        _client = redis.from_url(url, decode_responses=True)


def get_redis() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis is not initialised. Set REDIS_URL in your environment.")
    return _client

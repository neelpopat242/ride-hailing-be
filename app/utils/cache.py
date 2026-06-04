import json

from app.redis_client import get_redis

RIDE_TTL = 5
LOCATION_TTL = 10


class CacheService:
    def __init__(self):
        self.redis = get_redis()

    def get_ride(self, ride_id: str):
        raw = self.redis.get(f"ride:{ride_id}")
        return json.loads(raw) if raw else None

    def set_ride(self, ride_id: str, data: dict):
        self.redis.setex(f"ride:{ride_id}", RIDE_TTL, json.dumps(data))

    def invalidate_ride(self, ride_id: str):
        self.redis.delete(f"ride:{ride_id}")

    def get_location(self, driver_id: str):
        raw = self.redis.get(f"driver:{driver_id}:location")
        return json.loads(raw) if raw else None

    def set_location(self, driver_id: str, data: dict):
        self.redis.setex(f"driver:{driver_id}:location", LOCATION_TTL, json.dumps(data))

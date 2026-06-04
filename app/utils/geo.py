import math


def haversine_km(lat1, lng1, lat2, lng2):
    radius = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def pick_nearest_drivers(candidates, pickup_lat, pickup_lng, limit=5):
    """Return up to `limit` drivers sorted by distance from the pickup point."""
    eligible = [
        (haversine_km(pickup_lat, pickup_lng, driver.lat, driver.lng), driver)
        for driver in candidates
    ]
    eligible.sort(key=lambda item: item[0])
    return [driver for _, driver in eligible[:limit]]

def calculate_fare(distance_km, surge_multiplier=1.0):
    base_fare = 40.0
    per_km_rate = 12.0
    return round((base_fare + (per_km_rate * distance_km)) * surge_multiplier, 2)

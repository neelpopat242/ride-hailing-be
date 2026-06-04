"""
Seed script — creates users, drivers and prints their JWT tokens.

Usage:
    python seed.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.auth.jwt_auth import JWTAuth
from app.db import get_session
from app.models.driver import Driver
from app.models.user import User
from app.constants import DriverStatus

DRIVERS = [
    {"email": "driver1@example.com", "lat": 12.9352, "lng": 77.6245},
    {"email": "driver2@example.com", "lat": 12.9716, "lng": 77.5946},
    {"email": "driver3@example.com", "lat": 12.9611, "lng": 77.6387},
    {"email": "driver4@example.com", "lat": 12.9279, "lng": 77.6271},
    {"email": "driver5@example.com", "lat": 12.9830, "lng": 77.5800},
]

RIDERS = [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
]


def seed():
    app = create_app()
    with app.app_context():
        with get_session() as session:
            print("=== Riders ===")
            for rider_data in RIDERS:
                user = User(name=rider_data["name"], email=rider_data["email"])
                session.add(user)
                session.flush()
                token = JWTAuth.generate_token(str(user.id), "rider")
                print(f"{rider_data['name']}: id={user.id}  token={token}")

            print("\n=== Drivers ===")
            for idx, loc in enumerate(DRIVERS, start=1):
                driver = Driver(
                    email=loc["email"],
                    status=DriverStatus.AVAILABLE.value,
                    lat=loc["lat"],
                    lng=loc["lng"],
                )
                session.add(driver)
                session.flush()
                token = JWTAuth.generate_token(str(driver.id), "driver")
                print(f"Driver {idx}: id={driver.id}  token={token}")


if __name__ == "__main__":
    seed()

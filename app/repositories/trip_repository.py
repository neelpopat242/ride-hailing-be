import uuid
from datetime import UTC, datetime

from app.models.trip import Trip
from app.repositories.base_repository import BaseRepository


class TripRepository(BaseRepository):
    def create(self, ride_id):
        trip = Trip(ride_id=uuid.UUID(ride_id))
        self.session.add(trip)
        self.session.flush()
        return trip

    def get_by_id(self, trip_id):
        return self.session.get(Trip, uuid.UUID(trip_id))

    def get_by_ride_id(self, ride_id):
        return self.session.query(Trip).filter_by(ride_id=uuid.UUID(ride_id)).first()

    def start_trip(self, trip_id):
        trip = self.session.get(Trip, uuid.UUID(trip_id))
        if trip:
            trip.started_at = datetime.now(UTC)
            trip.updated_at = datetime.now(UTC)
        return trip

    def end_trip(self, trip_id, distance_km, fare_amount):
        trip = self.session.get(Trip, uuid.UUID(trip_id))
        if trip:
            trip.distance_km = distance_km
            trip.fare_amount = fare_amount
            trip.ended_at = datetime.now(UTC)
            trip.updated_at = datetime.now(UTC)
        return trip

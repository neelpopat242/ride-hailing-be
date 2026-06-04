import uuid
from datetime import UTC, datetime

from app.constants import RideStatus
from app.models.ride import Ride
from app.repositories.base_repository import BaseRepository


class RideRepository(BaseRepository):
    def create(self, payload, assigned_driver_id=None, status=RideStatus.REQUESTED.value):
        ride = Ride(
            rider_id=uuid.UUID(str(payload.get("rider_id"))),
            pickup_lat=payload["pickup_lat"],
            pickup_lng=payload["pickup_lng"],
            dest_lat=payload["dest_lat"],
            dest_lng=payload["dest_lng"],
            payment_method=payload["payment_method"],
            status=status,
            assigned_driver_id=uuid.UUID(assigned_driver_id) if assigned_driver_id else None,
        )
        self.session.add(ride)
        self.session.flush()
        return ride

    def get_by_id(self, ride_id):
        return self.session.get(Ride, uuid.UUID(ride_id))

    def update_status(self, ride_id, status):
        ride = self.session.get(Ride, uuid.UUID(ride_id))
        if ride:
            ride.status = status
            ride.updated_at = datetime.now(UTC)
        return ride

    def find_active_by_rider(self, rider_id):
        return (
            self.session.query(Ride)
            .filter(
                Ride.rider_id == uuid.UUID(str(rider_id)),
                Ride.status.in_([
                    RideStatus.REQUESTED.value,
                    RideStatus.ASSIGNED.value,
                    RideStatus.ACCEPTED.value,
                    RideStatus.IN_PROGRESS.value,
                ]),
            )
            .first()
        )

    def find_active_by_driver_id(self, driver_id):
        return (
            self.session.query(Ride)
            .filter(
                Ride.assigned_driver_id == uuid.UUID(driver_id),
                Ride.status.in_([RideStatus.ASSIGNED.value, RideStatus.ACCEPTED.value]),
            )
            .first()
        )

    def update_assignment(self, ride_id, driver_id, status):
        ride = self.session.get(Ride, uuid.UUID(ride_id))
        if ride:
            ride.assigned_driver_id = uuid.UUID(driver_id)
            ride.status = status
            ride.updated_at = datetime.now(UTC)
        return ride

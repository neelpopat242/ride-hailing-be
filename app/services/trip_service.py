from app.constants import DriverStatus, RideStatus
from app.exceptions import APIException
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_repository import RideRepository
from app.repositories.trip_repository import TripRepository
from app.schemas.response_schemas import TripEndResponse, TripStartResponse
from app.state_machine import DriverStateMachine, RideStateMachine
from app.utils.cache import CacheService
from app.utils.fare import calculate_fare
from app.utils.responses import success_response


class TripService:
    def __init__(self, session):
        self.trip_repo = TripRepository(session)
        self.ride_repo = RideRepository(session)
        self.driver_repo = DriverRepository(session)
        self.cache = CacheService()

    def start_trip(self, trip_id):
        trip = self.trip_repo.get_by_id(trip_id)
        if not trip:
            raise APIException("TRIP_NOT_FOUND", "Trip not found.", 404)

        ride = self.ride_repo.get_by_id(str(trip.ride_id))
        if not ride:
            raise APIException("RIDE_NOT_FOUND", "Ride not found.", 404)
        if ride.status != RideStatus.ACCEPTED.value:
            raise APIException("INVALID_TRIP_STATE", "Trip cannot be started in current state.", 409)

        RideStateMachine.transition(ride, RideStatus.IN_PROGRESS.value)
        self.trip_repo.start_trip(trip_id)
        self.cache.invalidate_ride(str(ride.id))

        response = TripStartResponse(
            trip_id=trip_id,
            ride_id=str(ride.id),
            status=RideStatus.IN_PROGRESS.value,
        )
        return success_response(response.model_dump(mode="json"))

    def end_trip(self, trip_id, payload):
        trip = self.trip_repo.get_by_id(trip_id)
        if not trip:
            raise APIException("TRIP_NOT_FOUND", "Trip not found.", 404)

        ride = self.ride_repo.get_by_id(str(trip.ride_id))
        if not ride:
            raise APIException("RIDE_NOT_FOUND", "Ride not found.", 404)
        if ride.status != RideStatus.IN_PROGRESS.value:
            raise APIException("INVALID_TRIP_STATE", "Trip cannot be ended in current state.", 409)

        fare_amount = calculate_fare(payload["distance_km"], trip.surge_multiplier or 1.0)
        self.trip_repo.end_trip(trip_id, payload["distance_km"], fare_amount)
        RideStateMachine.transition(ride, RideStatus.COMPLETED.value)
        self.cache.invalidate_ride(str(ride.id))

        if ride.assigned_driver_id:
            driver = self.driver_repo.get_by_id(str(ride.assigned_driver_id))
            if driver:
                DriverStateMachine.transition(driver, DriverStatus.AVAILABLE.value)

        response = TripEndResponse(
            trip_id=trip_id,
            ride_id=str(ride.id),
            status=RideStatus.COMPLETED.value,
            fare_amount=fare_amount,
            currency="INR",
        )
        return success_response(response.model_dump(mode="json"))

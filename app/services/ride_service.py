from app.constants import MAX_DISPATCH_CANDIDATES, RideStatus
from app.exceptions import APIException
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_candidate_repository import RideCandidateRepository
from app.repositories.ride_repository import RideRepository
from app.repositories.trip_repository import TripRepository
from app.schemas.response_schemas import LocationResponse, RideResponse
from app.services.dispatch_service import DispatchService
from app.utils.cache import CacheService
from app.utils.geo import pick_nearest_drivers
from app.utils.responses import success_response


class RideService:
    def __init__(self, session):
        self.ride_repo = RideRepository(session)
        self.driver_repo = DriverRepository(session)
        self.candidate_repo = RideCandidateRepository(session)
        self.trip_repo = TripRepository(session)
        self.dispatch = DispatchService(session)
        self.cache = CacheService()

    def create_ride(self, payload, rider_id):
        if self.ride_repo.find_active_by_rider(rider_id):
            raise APIException("RIDE_ALREADY_ACTIVE", "You already have an active ride.", 409)

        candidates = self.driver_repo.find_available_candidates()
        ordered_drivers = pick_nearest_drivers(
            candidates, payload.get("pickup_lat"), payload.get("pickup_lng"), MAX_DISPATCH_CANDIDATES
        )

        if not ordered_drivers:
            raise APIException("NO_DRIVERS_AVAILABLE", "No drivers available in your area.", 409)

        ride = self.ride_repo.create({**payload, "rider_id": rider_id}, status=RideStatus.REQUESTED.value)
        self.candidate_repo.bulk_create(str(ride.id), [str(d.id) for d in ordered_drivers])
        self.dispatch.dispatch_next(ride)

        trip = self.trip_repo.create(str(ride.id))
        response = RideResponse(
            ride_id=ride.id,
            trip_id=trip.id,
            status=ride.status,
            driver_id=ride.assigned_driver_id,
            offer_expires_at=ride.offer_expires_at,
        )
        return success_response(response.model_dump(mode="json"), 201)

    def get_ride(self, ride_id):
        cached = self.cache.get_ride(ride_id)
        if cached:
            return success_response(cached)

        ride = self.ride_repo.get_by_id(ride_id)
        if not ride:
            raise APIException("RIDE_NOT_FOUND", "Ride not found.", 404)

        self.dispatch.check_and_advance_timeout(ride)

        response = RideResponse(
            ride_id=ride.id,
            status=ride.status,
            driver_id=ride.assigned_driver_id,
            offer_expires_at=ride.offer_expires_at,
            payment_method=ride.payment_method,
            pickup_lat=ride.pickup_lat,
            pickup_lng=ride.pickup_lng,
            dest_lat=ride.dest_lat,
            dest_lng=ride.dest_lng,
        )
        data = response.model_dump(mode="json")
        self.cache.set_ride(ride_id, data)
        return success_response(data)

    def get_driver_location(self, ride_id):
        ride = self.ride_repo.get_by_id(ride_id)
        if not ride:
            raise APIException("RIDE_NOT_FOUND", "Ride not found.", 404)
        if not ride.assigned_driver_id:
            raise APIException("NO_DRIVER_ASSIGNED", "No driver assigned to this ride.", 404)

        driver_id = str(ride.assigned_driver_id)
        cached = self.cache.get_location(driver_id)
        if cached:
            return success_response(cached)

        driver = self.driver_repo.get_by_id(driver_id)
        if not driver or driver.lat is None:
            raise APIException("LOCATION_UNAVAILABLE", "Driver location not available yet.", 404)

        response = LocationResponse(
            driver_id=driver.id,
            lat=driver.lat,
            lng=driver.lng,
            updated_at=driver.location_updated_at,
        )
        return success_response(response.model_dump(mode="json"))

from app.constants import CandidateStatus, DriverStatus, RideStatus
from app.exceptions import APIException
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_candidate_repository import RideCandidateRepository
from app.repositories.ride_repository import RideRepository
from app.schemas.response_schemas import AcceptDeclineResponse, LocationResponse
from app.services.dispatch_service import DispatchService
from app.state_machine import DriverStateMachine, RideStateMachine
from app.utils.cache import CacheService
from app.utils.responses import success_response


class DriverService:
    def __init__(self, session):
        self.driver_repo = DriverRepository(session)
        self.ride_repo = RideRepository(session)
        self.candidate_repo = RideCandidateRepository(session)
        self.dispatch = DispatchService(session)
        self.cache = CacheService()

    def update_location(self, driver_id, payload):
        driver = self.driver_repo.get_by_id(driver_id)
        if not driver:
            raise APIException("DRIVER_NOT_FOUND", "Driver not found.", 404)

        if driver.status == DriverStatus.OFFLINE.value:
            raise APIException(
                "LOCATION_UPDATE_NOT_ALLOWED",
                "Location updates are not accepted while offline.",
                409,
            )

        driver = self.driver_repo.update_location(driver_id, payload)
        response = LocationResponse(
            driver_id=driver.id,
            lat=driver.lat,
            lng=driver.lng,
            updated_at=driver.location_updated_at,
        )
        data = response.model_dump(mode="json")
        self.cache.set_location(driver_id, data)
        return success_response(data)

    def accept_ride(self, driver_id, payload):
        driver = self.driver_repo.get_by_id(driver_id)
        ride = self.ride_repo.get_by_id(payload.get("ride_id"))
        if not driver or not ride:
            raise APIException("RESOURCE_NOT_FOUND", "Ride or driver not found.", 404)

        self.dispatch.check_and_advance_timeout(ride)

        if ride.status != RideStatus.ASSIGNED.value:
            raise APIException("INVALID_ASSIGNMENT_STATE", "Ride is no longer assignable.", 409)
        if str(ride.assigned_driver_id) != driver_id:
            raise APIException("INVALID_ASSIGNMENT_STATE", "Ride is not assigned to this driver.", 409)

        current = self.candidate_repo.get_current_offer(payload.get("ride_id"))
        if current:
            self.candidate_repo.update_status(current.id, CandidateStatus.ACCEPTED.value)
        self.candidate_repo.expire_others(payload.get("ride_id"), driver_id)

        RideStateMachine.transition(ride, RideStatus.ACCEPTED.value)
        DriverStateMachine.transition(driver, DriverStatus.ON_TRIP.value)
        self.cache.invalidate_ride(payload.get("ride_id"))

        response = AcceptDeclineResponse(
            ride_id=payload.get("ride_id"), driver_id=driver_id, status=RideStatus.ACCEPTED.value
        )
        return success_response(response.model_dump(mode="json"))

    def decline_ride(self, driver_id, payload):
        driver = self.driver_repo.get_by_id(driver_id)
        ride = self.ride_repo.get_by_id(payload.get("ride_id"))
        if not driver or not ride:
            raise APIException("RESOURCE_NOT_FOUND", "Ride or driver not found.", 404)

        self.dispatch.check_and_advance_timeout(ride)

        if ride.status not in (RideStatus.ASSIGNED.value, RideStatus.FAILED.value):
            raise APIException("INVALID_ASSIGNMENT_STATE", "Ride cannot be declined in current state.", 409)

        if ride.status == RideStatus.ASSIGNED.value and str(ride.assigned_driver_id) == driver_id:
            current = self.candidate_repo.get_current_offer(payload.get("ride_id"))
            if current:
                self.candidate_repo.update_status(current.id, CandidateStatus.DECLINED.value)
            self.dispatch.dispatch_next(ride)
        self.cache.invalidate_ride(payload.get("ride_id"))

        response = AcceptDeclineResponse(ride_id=payload.get("ride_id"), status=ride.status)
        return success_response(response.model_dump(mode="json"))

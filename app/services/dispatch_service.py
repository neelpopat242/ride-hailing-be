from datetime import UTC, datetime, timedelta

from app.constants import CandidateStatus, DriverStatus, OFFER_TIMEOUT_SECONDS, RideStatus
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_candidate_repository import RideCandidateRepository
from app.state_machine import DriverStateMachine, RideStateMachine
from app.utils.cache import CacheService


class DispatchService:
    """
    Owns all offer dispatching and timeout logic.
    Injected into RideService and DriverService — no circular imports.
    """

    def __init__(self, session):
        self.candidate_repo = RideCandidateRepository(session)
        self.driver_repo = DriverRepository(session)
        self.cache = CacheService()

    def dispatch_next(self, ride) -> bool:
        """
        Advance the offer to the next pending candidate.
        Releases the current driver back to available.
        Returns True if dispatched, False if no candidates remain (ride → FAILED).
        """
        if ride.assigned_driver_id:
            current_driver = self.driver_repo.get_by_id(str(ride.assigned_driver_id))
            if current_driver:
                DriverStateMachine.transition(current_driver, DriverStatus.AVAILABLE.value)

        next_candidate = self.candidate_repo.get_next_pending(str(ride.id))
        if not next_candidate:
            RideStateMachine.transition(ride, RideStatus.FAILED.value)
            ride.assigned_driver_id = None
            ride.offer_expires_at = None
            ride.updated_at = datetime.now(UTC)
            return False

        self.candidate_repo.update_status(next_candidate.id, CandidateStatus.OFFERED.value)

        next_driver = self.driver_repo.get_by_id(str(next_candidate.driver_id))
        if next_driver:
            DriverStateMachine.transition(next_driver, DriverStatus.ASSIGNED.value)

        RideStateMachine.transition(ride, RideStatus.ASSIGNED.value)
        ride.assigned_driver_id = next_candidate.driver_id
        ride.offer_expires_at = datetime.now(UTC) + timedelta(seconds=OFFER_TIMEOUT_SECONDS)
        ride.updated_at = datetime.now(UTC)
        self.cache.invalidate_ride(str(ride.id))
        return True

    def check_and_advance_timeout(self, ride) -> None:
        """
        If the active offer has expired, mark it expired and dispatch to the next candidate.
        Called lazily on GET /rides/{id}, accept, and decline.
        """
        if ride.status != RideStatus.ASSIGNED.value:
            return
        if ride.offer_expires_at and datetime.now(UTC) > ride.offer_expires_at:
            current = self.candidate_repo.get_current_offer(str(ride.id))
            if current:
                self.candidate_repo.update_status(current.id, CandidateStatus.EXPIRED.value)
            self.dispatch_next(ride)

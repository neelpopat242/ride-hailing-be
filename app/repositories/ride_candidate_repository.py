import uuid
from datetime import UTC, datetime

from app.constants import CandidateStatus
from app.models.ride_candidate import RideCandidate
from app.repositories.base_repository import BaseRepository


class RideCandidateRepository(BaseRepository):
    def bulk_create(self, ride_id, driver_ids_by_priority):
        """
        driver_ids_by_priority: list of driver_id strings ordered closest-first.
        """
        now = datetime.now(UTC)
        candidates = [
            RideCandidate(
                ride_id=uuid.UUID(ride_id),
                driver_id=uuid.UUID(driver_id),
                priority=idx + 1,
                status=CandidateStatus.PENDING.value,
                created_at=now,
                updated_at=now,
            )
            for idx, driver_id in enumerate(driver_ids_by_priority)
        ]
        self.session.add_all(candidates)
        self.session.flush()
        return candidates

    def get_current_offer(self, ride_id):
        return (
            self.session.query(RideCandidate)
            .filter_by(ride_id=uuid.UUID(ride_id), status=CandidateStatus.OFFERED.value)
            .first()
        )

    def get_next_pending(self, ride_id):
        return (
            self.session.query(RideCandidate)
            .filter_by(ride_id=uuid.UUID(ride_id), status=CandidateStatus.PENDING.value)
            .order_by(RideCandidate.priority)
            .first()
        )

    def expire_others(self, ride_id, accepted_driver_id):
        """Mark all non-accepted candidates for a ride as EXPIRED."""
        (
            self.session.query(RideCandidate)
            .filter(
                RideCandidate.ride_id == uuid.UUID(ride_id),
                RideCandidate.driver_id != uuid.UUID(accepted_driver_id),
                RideCandidate.status.in_([
                    CandidateStatus.PENDING.value,
                    CandidateStatus.OFFERED.value,
                ]),
            )
            .update(
                {"status": CandidateStatus.EXPIRED.value, "updated_at": datetime.now(UTC)},
                synchronize_session="fetch",
            )
        )

    def update_status(self, candidate_id, status):
        candidate = self.session.get(RideCandidate, candidate_id)
        if candidate:
            candidate.status = status
            candidate.updated_at = datetime.now(UTC)
        return candidate

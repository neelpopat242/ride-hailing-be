from enum import Enum


class DriverStatus(str, Enum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    ON_TRIP = "on_trip"
    OFFLINE = "offline"


class RideStatus(str, Enum):
    REQUESTED = "requested"
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PaymentStatus(str, Enum):
    INITIATED = "initiated"
    SUCCESS = "success"
    FAILED = "failed"


class CandidateStatus(str, Enum):
    PENDING = "pending"      # queued, not yet offered
    OFFERED = "offered"      # current active offer
    ACCEPTED = "accepted"    # driver accepted
    DECLINED = "declined"    # driver declined
    EXPIRED = "expired"      # offer timed out


OFFER_TIMEOUT_SECONDS = 10
MAX_DISPATCH_CANDIDATES = 5

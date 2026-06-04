from app.constants import DriverStatus, RideStatus
from app.exceptions import APIException


# Allowed transitions: current_state -> set of valid next states
RIDE_TRANSITIONS: dict[str, set[str]] = {
    RideStatus.REQUESTED.value:  {RideStatus.ASSIGNED.value, RideStatus.FAILED.value},
    RideStatus.ASSIGNED.value:   {RideStatus.ACCEPTED.value, RideStatus.ASSIGNED.value, RideStatus.FAILED.value},
    RideStatus.ACCEPTED.value:   {RideStatus.IN_PROGRESS.value, RideStatus.COMPLETED.value, RideStatus.CANCELLED.value},
    RideStatus.IN_PROGRESS.value:{RideStatus.COMPLETED.value, RideStatus.CANCELLED.value},
    RideStatus.COMPLETED.value:  set(),
    RideStatus.CANCELLED.value:  set(),
    RideStatus.FAILED.value:     set(),
}

DRIVER_TRANSITIONS: dict[str, set[str]] = {
    DriverStatus.AVAILABLE.value: {DriverStatus.ASSIGNED.value, DriverStatus.OFFLINE.value},
    DriverStatus.ASSIGNED.value:  {DriverStatus.ON_TRIP.value, DriverStatus.AVAILABLE.value},
    DriverStatus.ON_TRIP.value:   {DriverStatus.AVAILABLE.value},
    DriverStatus.OFFLINE.value:   {DriverStatus.AVAILABLE.value},
}


class RideStateMachine:
    """
    Validates and applies ride status transitions.
    Raises APIException for any illegal transition.
    """

    @staticmethod
    def transition(ride, new_status: str) -> None:
        allowed = RIDE_TRANSITIONS.get(ride.status, set())
        if new_status not in allowed:
            raise APIException(
                "INVALID_STATE_TRANSITION",
                f"Ride cannot move from '{ride.status}' to '{new_status}'.",
                409,
            )
        ride.status = new_status


class DriverStateMachine:
    """
    Validates and applies driver status transitions.
    Raises APIException for any illegal transition.
    """

    @staticmethod
    def transition(driver, new_status: str) -> None:
        allowed = DRIVER_TRANSITIONS.get(driver.status, set())
        if new_status not in allowed:
            raise APIException(
                "INVALID_STATE_TRANSITION",
                f"Driver cannot move from '{driver.status}' to '{new_status}'.",
                409,
            )
        driver.status = new_status

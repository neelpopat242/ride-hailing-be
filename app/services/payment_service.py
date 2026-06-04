from datetime import UTC, datetime

from app.exceptions import APIException
from app.repositories.payment_repository import PaymentRepository
from app.repositories.ride_repository import RideRepository
from app.repositories.trip_repository import TripRepository
from app.schemas.response_schemas import PaymentResponse
from app.utils.responses import success_response


class PaymentService:
    def __init__(self, session):
        self.payment_repo = PaymentRepository(session)
        self.ride_repo = RideRepository(session)
        self.trip_repo = TripRepository(session)

    def create_payment(self, payload):
        ride = self.ride_repo.get_by_id(payload.get("ride_id"))
        trip = self.trip_repo.get_by_ride_id(payload.get("ride_id"))

        if not ride or not trip or trip.fare_amount is None:
            raise APIException("PAYMENT_NOT_READY", "Ride or trip is not ready for payment.", 409)

        psp_ref = f"PSP-{payload.get('ride_id')}-{int(datetime.now(UTC).timestamp())}"
        payment = self.payment_repo.create_success(payload.get("ride_id"), trip.fare_amount, psp_ref)

        response = PaymentResponse(
            payment_id=payment.id,
            ride_id=payment.ride_id,
            amount=payment.amount,
            status=payment.status,
            psp_reference=payment.psp_reference,
        )
        return success_response(response.model_dump(mode="json"), 201)

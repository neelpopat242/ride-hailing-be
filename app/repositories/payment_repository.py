import uuid

from app.constants import PaymentStatus
from app.models.payment import Payment
from app.repositories.base_repository import BaseRepository


class PaymentRepository(BaseRepository):
    def create_success(self, ride_id, amount, psp_reference):
        payment = Payment(
            ride_id=uuid.UUID(ride_id),
            amount=amount,
            currency="INR",
            status=PaymentStatus.SUCCESS.value,
            psp_reference=psp_reference,
        )
        self.session.add(payment)
        self.session.flush()
        return payment

from app.schemas.payment_schemas import PaymentCreateSchema
from app.services.payment_service import PaymentService
from app.views.base import ViewSet, route


class PaymentViewSet(ViewSet):

    def __init__(self, session):
        super().__init__(session)
        self.payment_service = PaymentService(session)

    @route("POST", "", schema=PaymentCreateSchema, auth=["rider"])
    def create(self):
        return self.payment_service.create_payment(self.validated_data)

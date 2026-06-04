from app.schemas.common import BaseSchema


class PaymentCreateSchema(BaseSchema):
    ride_id: str

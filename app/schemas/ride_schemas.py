from pydantic import Field

from app.schemas.common import BaseSchema


class RideCreateSchema(BaseSchema):
    pickup_lat: float = Field(ge=-90, le=90)
    pickup_lng: float = Field(ge=-180, le=180)
    dest_lat: float = Field(ge=-90, le=90)
    dest_lng: float = Field(ge=-180, le=180)
    payment_method: str

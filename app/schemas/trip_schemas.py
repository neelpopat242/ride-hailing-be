from pydantic import Field

from app.schemas.common import BaseSchema


class TripEndSchema(BaseSchema):
    distance_km: float = Field(gt=0)

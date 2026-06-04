from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import BaseSchema


class DriverLocationSchema(BaseSchema):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    updated_at: Optional[datetime] = None


class DriverAcceptSchema(BaseSchema):
    ride_id: str


class DriverDeclineSchema(BaseSchema):
    ride_id: str

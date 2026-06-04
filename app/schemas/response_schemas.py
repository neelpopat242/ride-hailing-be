from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class RideResponse(BaseModel):
    ride_id: UUID
    trip_id: Optional[UUID] = None
    status: str
    driver_id: Optional[UUID] = None
    offer_expires_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    dest_lat: Optional[float] = None
    dest_lng: Optional[float] = None


class LocationResponse(BaseModel):
    driver_id: UUID
    lat: float
    lng: float
    updated_at: datetime


class AcceptDeclineResponse(BaseModel):
    ride_id: UUID
    driver_id: Optional[UUID] = None
    status: str


class TripStartResponse(BaseModel):
    trip_id: UUID
    ride_id: UUID
    status: str


class TripEndResponse(BaseModel):
    trip_id: UUID
    ride_id: UUID
    status: str
    fare_amount: float
    currency: str


class PaymentResponse(BaseModel):
    payment_id: UUID
    ride_id: UUID
    amount: float
    status: str
    psp_reference: str

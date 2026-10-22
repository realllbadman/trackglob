from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---------------------------------------------------------------- public
class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    notes: Optional[str] = None
    updated_by: Optional[str] = None
    timestamp: Optional[datetime] = None


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tracking_number: str
    sender_name: str
    sender_address: Optional[str] = None
    receiver_name: str
    receiver_phone: Optional[str] = None
    receiver_address: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    package_type: Optional[str] = None
    weight: Optional[str] = None
    service_type: Optional[str] = None
    current_status: str
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    estimated_delivery: Optional[str] = None
    created_at: Optional[datetime] = None
    carrier: Optional[str] = None
    carrier_reference: Optional[str] = None
    shipment_mode: Optional[str] = None
    product: Optional[str] = None
    qty: Optional[str] = None
    piece_type: Optional[str] = None
    payment_mode: Optional[str] = None
    total_freight: Optional[str] = None
    departure_time: Optional[str] = None
    pickup_date: Optional[str] = None
    pickup_time: Optional[str] = None
    length_cm: Optional[str] = None
    width_cm: Optional[str] = None
    height_cm: Optional[str] = None
    comments: Optional[str] = None
    journey_origin: Optional[str] = None
    journey_destination: Optional[str] = None
    journey_state: Optional[str] = None


class TrackingResultOut(BaseModel):
    shipment: ShipmentOut
    events: List[EventOut]
    route_path: Optional[List[List[float]]] = None
    journey_start: Optional[str] = None
    journey_end: Optional[str] = None
    journey_state: str = "not_started"
    journey_paused_frac: Optional[float] = None
    server_now: str


class SubscribeIn(BaseModel):
    email: EmailStr


# ---------------------------------------------------------------- customer
class RegisterIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("first_name", "last_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TrackingNumberIn(BaseModel):
    tracking_number: str = Field(min_length=3, max_length=32)


class NotifyIn(BaseModel):
    notify_email: bool


# ---------------------------------------------------------------- admin
class _ShipmentFields(BaseModel):
    sender_address: Optional[str] = None
    receiver_phone: Optional[str] = None
    receiver_address: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    package_type: Optional[str] = None
    weight: Optional[str] = None
    service_type: Optional[str] = None
    estimated_delivery: Optional[str] = None
    carrier: Optional[str] = None
    carrier_reference: Optional[str] = None
    shipment_mode: Optional[str] = None
    product: Optional[str] = None
    qty: Optional[str] = None
    piece_type: Optional[str] = None
    payment_mode: Optional[str] = None
    total_freight: Optional[str] = None
    departure_time: Optional[str] = None
    pickup_date: Optional[str] = None
    pickup_time: Optional[str] = None
    length_cm: Optional[str] = None
    width_cm: Optional[str] = None
    height_cm: Optional[str] = None
    comments: Optional[str] = None


class ShipmentCreate(_ShipmentFields):
    sender_name: str = Field(min_length=1, max_length=160)
    receiver_name: str = Field(min_length=1, max_length=160)
    receiver_email: EmailStr
    customer_email: Optional[EmailStr] = None
    notify_email: bool = True

    @field_validator("customer_email", mode="before")
    @classmethod
    def _blank_none(cls, v):
        return v or None


class ShipmentUpdate(_ShipmentFields):
    sender_name: Optional[str] = Field(default=None, max_length=160)
    receiver_name: Optional[str] = Field(default=None, max_length=160)
    receiver_email: Optional[EmailStr] = None
    current_status: Optional[str] = None
    notify_email: Optional[bool] = None


class EventCreate(BaseModel):
    status: str
    location_name: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = Field(default=None, max_length=2000)
    updated_by: Optional[str] = Field(default=None, max_length=120)


class RouteIn(BaseModel):
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    waypoints: List[str] = []


class JourneyStartIn(BaseModel):
    journey_start: Optional[datetime] = None
    journey_end: datetime

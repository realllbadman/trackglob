from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.types import TypeDecorator

from .database import Base

STATUS_VALUES = [
    "Pending",
    "Picked Up",
    "In Transit",
    "Arrived at Hub",
    "Departed Hub",
    "Out for Delivery",
    "Delivered",
    "Exception / Delayed",
    "Held at Customs",
    "On Hold / Delayed",
]

IN_TRANSIT_STATUSES = ["Picked Up", "In Transit", "Arrived at Hub", "Departed Hub", "Out for Delivery"]

JOURNEY_STATES = ["not_started", "moving", "paused", "arrived"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in SQLite, always returns tz-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(80), nullable=False)
    last_name = Column(String(80), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(40), nullable=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(UTCDateTime(), default=utcnow)
    last_login = Column(UTCDateTime(), nullable=True)


class Shipment(Base):
    __tablename__ = "shipments"

    # Identity
    id = Column(Integer, primary_key=True, index=True)
    tracking_number = Column(String(32), unique=True, index=True, nullable=False)
    customer_id = Column(Integer, nullable=True, index=True)  # soft FK

    # Parties
    sender_name = Column(String(160), nullable=False)
    sender_address = Column(Text, nullable=True)
    receiver_name = Column(String(160), nullable=False)
    receiver_email = Column(String(255), nullable=False, index=True)
    receiver_phone = Column(String(40), nullable=True)
    receiver_address = Column(Text, nullable=True)

    # Basics
    origin = Column(String(255), nullable=True)
    destination = Column(String(255), nullable=True)
    package_type = Column(String(40), nullable=True)
    weight = Column(String(40), nullable=True)
    service_type = Column(String(40), nullable=True)

    # Live state
    current_status = Column(String(40), default="Pending", nullable=False)
    current_lat = Column(Float, nullable=True)
    current_lng = Column(Float, nullable=True)
    estimated_delivery = Column(String(80), nullable=True)
    notify_email = Column(Integer, default=1, nullable=False)
    created_at = Column(UTCDateTime(), default=utcnow)

    # Extended details
    carrier = Column(Text, nullable=True)
    carrier_reference = Column(Text, nullable=True)
    shipment_mode = Column(Text, nullable=True)
    product = Column(Text, nullable=True)
    qty = Column(Text, nullable=True)
    piece_type = Column(Text, nullable=True)
    payment_mode = Column(Text, nullable=True)
    total_freight = Column(Text, nullable=True)
    departure_time = Column(Text, nullable=True)
    pickup_date = Column(Text, nullable=True)
    pickup_time = Column(Text, nullable=True)
    length_cm = Column(Text, nullable=True)
    width_cm = Column(Text, nullable=True)
    height_cm = Column(Text, nullable=True)
    comments = Column(Text, nullable=True)

    # Animated journey
    journey_origin = Column(Text, nullable=True)
    journey_destination = Column(Text, nullable=True)
    journey_waypoints = Column(Text, nullable=True)  # JSON list[str]
    route_path = Column(Text, nullable=True)  # JSON list[[lat, lng]]
    journey_start = Column(UTCDateTime(), nullable=True)
    journey_end = Column(UTCDateTime(), nullable=True)
    journey_paused_at = Column(UTCDateTime(), nullable=True)
    journey_paused_frac = Column(Float, nullable=True)
    journey_state = Column(String(20), default="not_started", nullable=False)


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, nullable=False, index=True)
    status = Column(String(40), nullable=False)
    location_name = Column(String(255), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    updated_by = Column(String(120), nullable=True)
    timestamp = Column(UTCDateTime(), default=utcnow)


class ShipmentWatch(Base):
    __tablename__ = "shipment_watches"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, nullable=False, index=True)
    shipment_id = Column(Integer, nullable=False, index=True)
    created_at = Column(UTCDateTime(), default=utcnow)


class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    created_at = Column(UTCDateTime(), default=utcnow)


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String(500), unique=True, index=True, nullable=False)
    lat = Column(Float, nullable=True)  # null = cached "not found"
    lng = Column(Float, nullable=True)
    created_at = Column(UTCDateTime(), default=utcnow)

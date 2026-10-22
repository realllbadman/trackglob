import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin
from ..database import get_db
from ..geocode import geocode
from ..models import (
    IN_TRANSIT_STATUSES,
    STATUS_VALUES,
    Customer,
    Shipment,
    ShipmentWatch,
    Subscriber,
    TrackingEvent,
    utcnow,
)
from ..routing import get_road_route
from ..schemas import EventCreate, JourneyStartIn, RouteIn, ShipmentCreate, ShipmentUpdate
from ..services.email import send_journey_update, send_shipment_created, send_status_update
from ..utils import as_utc, generate_tracking_number, iso
from .customer import customer_dict, customer_shipments, owned_filter
from .tracking import event_dict, parse_route, shipment_events

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _get_shipment(db: Session, shipment_id: int) -> Shipment:
    shipment = db.get(Shipment, shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


def _shipment_full(db: Session, s: Shipment) -> dict:
    data = {}
    for col in Shipment.__table__.columns:
        val = getattr(s, col.name)
        data[col.name] = iso(val) if isinstance(val, datetime) else val
    data["notify_email"] = bool(s.notify_email)
    data["route_path"] = parse_route(s)
    try:
        data["journey_waypoints"] = json.loads(s.journey_waypoints) if s.journey_waypoints else []
    except ValueError:
        data["journey_waypoints"] = []
    data["events"] = [event_dict(ev) for ev in shipment_events(db, s.id)]
    data["server_now"] = iso(utcnow())
    return data


def _list_row(s: Shipment) -> dict:
    return {
        "id": s.id,
        "tracking_number": s.tracking_number,
        "receiver_name": s.receiver_name,
        "receiver_email": s.receiver_email,
        "destination": s.destination,
        "current_status": s.current_status,
        "journey_state": s.journey_state,
        "created_at": iso(s.created_at),
    }


def _clean(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


# ---------------------------------------------------------------- stats
@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = db.query(func.count(Shipment.id))
    return {
        "total": q.scalar() or 0,
        "in_transit": q.filter(Shipment.current_status.in_(IN_TRANSIT_STATUSES)).scalar() or 0,
        "delivered": db.query(func.count(Shipment.id)).filter(Shipment.current_status == "Delivered").scalar() or 0,
        "pending": db.query(func.count(Shipment.id)).filter(Shipment.current_status == "Pending").scalar() or 0,
        "this_month": db.query(func.count(Shipment.id)).filter(Shipment.created_at >= month_start).scalar() or 0,
        "statuses": STATUS_VALUES,
    }


# ---------------------------------------------------------------- shipments
@router.post("/shipments")
def create_shipment(payload: ShipmentCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    data = {k: _clean(v) for k, v in payload.model_dump().items()}
    customer_email = (data.pop("customer_email") or "").lower() or None
    notify = 1 if data.pop("notify_email") else 0
    data["receiver_email"] = data["receiver_email"].lower()

    customer_id = None
    if customer_email:
        c = db.query(Customer).filter(func.lower(Customer.email) == customer_email).first()
        if not c:
            raise HTTPException(status_code=400, detail=f"No customer account with email {customer_email}")
        customer_id = c.id
    else:
        c = db.query(Customer).filter(func.lower(Customer.email) == data["receiver_email"]).first()
        if c:
            customer_id = c.id

    shipment = Shipment(
        tracking_number=generate_tracking_number(db),
        customer_id=customer_id,
        notify_email=notify,
        current_status="Pending",
        **data,
    )
    point = geocode(shipment.origin) if shipment.origin else None
    if point:
        shipment.current_lat, shipment.current_lng = point
    db.add(shipment)
    db.flush()
    db.add(
        TrackingEvent(
            shipment_id=shipment.id,
            status="Pending",
            location_name=shipment.origin,
            lat=point[0] if point else None,
            lng=point[1] if point else None,
            notes="Shipment created",
            updated_by="System",
        )
    )
    db.commit()
    background.add_task(send_shipment_created, shipment)
    return {"ok": True, "tracking_number": shipment.tracking_number, "id": shipment.id}


@router.get("/shipments")
def list_shipments(q: str = "", status_filter: str = "", db: Session = Depends(get_db)):
    query = db.query(Shipment)
    q = q.strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Shipment.tracking_number.ilike(like),
                Shipment.receiver_name.ilike(like),
                Shipment.receiver_email.ilike(like),
                Shipment.destination.ilike(like),
            )
        )
    if status_filter:
        query = query.filter(Shipment.current_status == status_filter)
    rows = query.order_by(Shipment.created_at.desc(), Shipment.id.desc()).limit(500).all()
    return [_list_row(s) for s in rows]


@router.get("/shipments/{shipment_id}")
def get_shipment(shipment_id: int, db: Session = Depends(get_db)):
    return _shipment_full(db, _get_shipment(db, shipment_id))


@router.patch("/shipments/{shipment_id}")
def update_shipment(shipment_id: int, payload: ShipmentUpdate, db: Session = Depends(get_db)):
    shipment = _get_shipment(db, shipment_id)
    data = payload.model_dump(exclude_unset=True)
    if "receiver_email" in data:
        if not data["receiver_email"]:
            raise HTTPException(status_code=400, detail="Receiver email is required")
        data["receiver_email"] = data["receiver_email"].strip().lower()
    if "notify_email" in data:
        data["notify_email"] = 1 if data["notify_email"] else 0
    if "current_status" in data and data["current_status"] not in STATUS_VALUES:
        raise HTTPException(status_code=400, detail="Invalid status")
    for required in ("sender_name", "receiver_name"):
        if required in data and not (data[required] or "").strip():
            raise HTTPException(status_code=400, detail=f"{required.replace('_', ' ').title()} is required")
    for k, v in data.items():
        setattr(shipment, k, _clean(v) if k not in ("notify_email",) else v)
    db.commit()
    return _shipment_full(db, shipment)


@router.delete("/shipments/{shipment_id}")
def delete_shipment(shipment_id: int, db: Session = Depends(get_db)):
    shipment = _get_shipment(db, shipment_id)
    db.query(TrackingEvent).filter(TrackingEvent.shipment_id == shipment.id).delete(synchronize_session=False)
    db.query(ShipmentWatch).filter(ShipmentWatch.shipment_id == shipment.id).delete(synchronize_session=False)
    db.delete(shipment)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- events
@router.post("/shipments/{shipment_id}/events")
def add_event(shipment_id: int, payload: EventCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    shipment = _get_shipment(db, shipment_id)
    if payload.status not in STATUS_VALUES:
        raise HTTPException(status_code=400, detail="Invalid status")
    location = _clean(payload.location_name)
    point = geocode(location) if location else None
    event = TrackingEvent(
        shipment_id=shipment.id,
        status=payload.status,
        location_name=location,
        lat=point[0] if point else None,
        lng=point[1] if point else None,
        notes=_clean(payload.notes),
        updated_by=_clean(payload.updated_by) or "Admin",
        timestamp=utcnow(),
    )
    db.add(event)
    shipment.current_status = payload.status
    if point:
        shipment.current_lat, shipment.current_lng = point
    if payload.status == "Delivered" and not shipment.estimated_delivery:
        shipment.estimated_delivery = utcnow().strftime("%b %d, %Y")
    db.commit()
    if shipment.notify_email:
        background.add_task(send_status_update, shipment, event)
    return {"ok": True, "event": event_dict(event), "geocoded": bool(point)}


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(TrackingEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    shipment = db.get(Shipment, event.shipment_id)
    db.delete(event)
    db.flush()
    if shipment:
        remaining = shipment_events(db, shipment.id)
        if remaining:
            latest = remaining[-1]
            shipment.current_status = latest.status
            located = next((ev for ev in reversed(remaining) if ev.lat is not None), None)
            shipment.current_lat = located.lat if located else None
            shipment.current_lng = located.lng if located else None
        else:
            shipment.current_status = "Pending"
            shipment.current_lat = None
            shipment.current_lng = None
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- customers
@router.get("/customers")
def list_customers(db: Session = Depends(get_db)):
    customers = (
        db.query(Customer)
        .order_by(Customer.last_login.is_(None), Customer.last_login.desc(), Customer.created_at.desc())
        .all()
    )
    out = []
    for c in customers:
        row = customer_dict(c)
        row["shipment_count"] = db.query(func.count(Shipment.id)).filter(owned_filter(c)).scalar() or 0
        out.append(row)
    return out


@router.get("/customers/{customer_id}/shipments")
def customer_detail(customer_id: int, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"customer": customer_dict(c), "shipments": customer_shipments(db, c)}


@router.post("/customers/{customer_id}/reset-password")
def reset_password(customer_id: int, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    temp = secrets.token_urlsafe(6)
    c.password_hash = hash_password(temp)
    db.commit()
    return {"ok": True, "temp_password": temp, "email": c.email}


# ---------------------------------------------------------------- subscribers
@router.get("/subscribers")
def list_subscribers(db: Session = Depends(get_db)):
    rows = db.query(Subscriber).order_by(Subscriber.created_at.desc(), Subscriber.id.desc()).all()
    return [{"id": s.id, "email": s.email, "created_at": iso(s.created_at)} for s in rows]


# ---------------------------------------------------------------- journey
def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@router.post("/shipments/{shipment_id}/route")
def build_route(shipment_id: int, payload: RouteIn, db: Session = Depends(get_db)):
    shipment = _get_shipment(db, shipment_id)
    waypoints = [w.strip() for w in payload.waypoints if w and w.strip()]
    stops = [payload.origin.strip(), *waypoints, payload.destination.strip()]
    path = get_road_route(stops)
    if len(path) < 2:
        raise HTTPException(
            status_code=400,
            detail="Could not locate at least two of the stops. Try more specific addresses (city, country).",
        )
    shipment.journey_origin = payload.origin.strip()
    shipment.journey_destination = payload.destination.strip()
    shipment.journey_waypoints = json.dumps(waypoints)
    shipment.route_path = json.dumps(path)
    db.commit()
    return {"route_path": path, "points": len(path)}


def _to_utc(dt: datetime) -> datetime:
    # naive datetimes are interpreted as UTC
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@router.post("/shipments/{shipment_id}/journey/start")
def journey_start(shipment_id: int, payload: JourneyStartIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    shipment = _get_shipment(db, shipment_id)
    if not parse_route(shipment):
        raise HTTPException(status_code=400, detail="Build a route first")
    start = _to_utc(payload.journey_start) if payload.journey_start else utcnow()
    end = _to_utc(payload.journey_end)
    if end <= start:
        raise HTTPException(status_code=400, detail="Arrival (ETA) must be after departure")
    shipment.journey_start = start
    shipment.journey_end = end
    shipment.journey_state = "moving"
    shipment.journey_paused_at = None
    shipment.journey_paused_frac = None
    if shipment.current_status in ("Pending", "On Hold / Delayed", "Picked Up"):
        shipment.current_status = "In Transit"
    shipment.estimated_delivery = end.strftime("%b %d, %Y %H:%M UTC")
    db.commit()
    background.add_task(send_journey_update, shipment, "moving")
    return _shipment_full(db, shipment)


@router.post("/shipments/{shipment_id}/journey/pause")
def journey_pause(shipment_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    shipment = _get_shipment(db, shipment_id)
    if shipment.journey_state != "moving":
        raise HTTPException(status_code=400, detail="Journey is not moving")
    now = utcnow()
    start, end = as_utc(shipment.journey_start), as_utc(shipment.journey_end)
    total = (end - start).total_seconds() if start and end else 0
    shipment.journey_paused_frac = _clamp((now - start).total_seconds() / total) if total > 0 else 0.0
    shipment.journey_paused_at = now
    shipment.journey_state = "paused"
    shipment.current_status = "On Hold / Delayed"
    db.commit()
    background.add_task(send_journey_update, shipment, "held")
    return _shipment_full(db, shipment)


@router.post("/shipments/{shipment_id}/journey/resume")
def journey_resume(shipment_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    shipment = _get_shipment(db, shipment_id)
    if shipment.journey_state != "paused":
        raise HTTPException(status_code=400, detail="Journey is not paused")
    now = utcnow()
    paused_at = as_utc(shipment.journey_paused_at) or now
    pause_len = now - paused_at
    # shift both ends so the parcel resumes from exactly where it froze
    shipment.journey_end = as_utc(shipment.journey_end) + pause_len
    shipment.journey_start = as_utc(shipment.journey_start) + pause_len
    shipment.journey_paused_at = None
    shipment.journey_paused_frac = None
    shipment.journey_state = "moving"
    shipment.current_status = "In Transit"
    shipment.estimated_delivery = shipment.journey_end.strftime("%b %d, %Y %H:%M UTC")
    db.commit()
    background.add_task(send_journey_update, shipment, "moving")
    return _shipment_full(db, shipment)


@router.post("/shipments/{shipment_id}/journey/arrive")
def journey_arrive(shipment_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    shipment = _get_shipment(db, shipment_id)
    path = parse_route(shipment)
    if not path:
        raise HTTPException(status_code=400, detail="Build a route first")
    shipment.journey_state = "arrived"
    shipment.journey_paused_at = None
    shipment.journey_paused_frac = None
    shipment.current_lat, shipment.current_lng = path[-1][0], path[-1][1]
    if shipment.current_status != "Delivered":
        shipment.current_status = "Out for Delivery"
    db.commit()
    background.add_task(send_journey_update, shipment, "final")
    return _shipment_full(db, shipment)

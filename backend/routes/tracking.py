import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Shipment, TrackingEvent
from ..schemas import EventOut, ShipmentOut, TrackingResultOut
from ..utils import iso

router = APIRouter(prefix="/api/track", tags=["tracking"])


def find_shipment(db: Session, tn: str):
    tn = (tn or "").strip().upper()
    if not tn:
        return None
    return db.query(Shipment).filter(Shipment.tracking_number == tn).first()


def shipment_events(db: Session, shipment_id: int):
    return (
        db.query(TrackingEvent)
        .filter(TrackingEvent.shipment_id == shipment_id)
        .order_by(TrackingEvent.timestamp.asc(), TrackingEvent.id.asc())
        .all()
    )


def parse_route(shipment) -> list | None:
    if not shipment.route_path:
        return None
    try:
        path = json.loads(shipment.route_path)
        return path if isinstance(path, list) and len(path) >= 2 else None
    except (ValueError, TypeError):
        return None


def journey_payload(shipment) -> dict:
    return {
        "start": iso(shipment.journey_start),
        "end": iso(shipment.journey_end),
        "state": shipment.journey_state or "not_started",
        "paused_frac": shipment.journey_paused_frac,
    }


def server_now_iso() -> str:
    return iso(datetime.now(timezone.utc))


def event_dict(ev) -> dict:
    return {
        "id": ev.id,
        "status": ev.status,
        "location_name": ev.location_name,
        "lat": ev.lat,
        "lng": ev.lng,
        "notes": ev.notes,
        "updated_by": ev.updated_by,
        "timestamp": iso(ev.timestamp),
    }


@router.get("/{tn}", response_model=TrackingResultOut)
def track(tn: str, db: Session = Depends(get_db)):
    shipment = find_shipment(db, tn)
    if not shipment:
        raise HTTPException(status_code=404, detail="Tracking number not found")
    events = shipment_events(db, shipment.id)
    j = journey_payload(shipment)
    return TrackingResultOut(
        shipment=ShipmentOut.model_validate(shipment),
        events=[EventOut(**event_dict(ev)) for ev in events],
        route_path=parse_route(shipment),
        journey_start=j["start"],
        journey_end=j["end"],
        journey_state=j["state"],
        journey_paused_frac=j["paused_frac"],
        server_now=server_now_iso(),
    )

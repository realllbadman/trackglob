from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..auth import (
    clear_session_cookie,
    get_current_customer,
    hash_password,
    require_customer,
    set_session_cookie,
    verify_password,
)
from ..database import get_db
from ..models import Customer, Shipment, ShipmentWatch, utcnow
from ..schemas import LoginIn, NotifyIn, RegisterIn, TrackingNumberIn
from ..services.email import send_welcome
from ..utils import RateLimiter, client_ip, iso
from .tracking import find_shipment

router = APIRouter(prefix="/api/customer", tags=["customer"])

login_limiter = RateLimiter(max_hits=10, window_seconds=15 * 60)
register_limiter = RateLimiter(max_hits=5, window_seconds=60 * 60)


def customer_dict(c: Customer) -> dict:
    return {
        "id": c.id,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "email": c.email,
        "phone": c.phone,
        "created_at": iso(c.created_at),
        "last_login": iso(c.last_login),
    }


def owned_filter(customer: Customer):
    """Ownership rule: linked by id OR receiver_email matches (case-insensitive)."""
    return or_(
        Shipment.customer_id == customer.id,
        func.lower(Shipment.receiver_email) == customer.email.lower(),
    )


def is_owner(shipment: Shipment, customer: Customer) -> bool:
    return shipment.customer_id == customer.id or (
        (shipment.receiver_email or "").lower() == customer.email.lower()
    )


def shipment_row(s: Shipment, source: str) -> dict:
    return {
        "id": s.id,
        "tracking_number": s.tracking_number,
        "receiver_name": s.receiver_name,
        "destination": s.destination,
        "current_status": s.current_status,
        "notify_email": bool(s.notify_email),
        "source": source,
        "created_at": iso(s.created_at),
    }


def customer_shipments(db: Session, customer: Customer) -> list:
    owned = db.query(Shipment).filter(owned_filter(customer)).all()
    owned_ids = {s.id for s in owned}
    watched_ids = [w.shipment_id for w in db.query(ShipmentWatch).filter(ShipmentWatch.customer_id == customer.id)]
    followed = []
    if watched_ids:
        followed = [s for s in db.query(Shipment).filter(Shipment.id.in_(watched_ids)) if s.id not in owned_ids]
    rows = [shipment_row(s, "owned") for s in owned] + [shipment_row(s, "followed") for s in followed]
    rows.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return rows


@router.post("/register")
def register(payload: RegisterIn, request: Request, response: Response, background: BackgroundTasks, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if register_limiter.blocked(ip):
        raise HTTPException(status_code=429, detail="Too many sign-ups from this address. Please try again later.")
    register_limiter.hit(ip)

    email = payload.email.strip().lower()
    if db.query(Customer.id).filter(func.lower(Customer.email) == email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    customer = Customer(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=email,
        phone=(payload.phone or "").strip() or None,
        password_hash=hash_password(payload.password),
        last_login=utcnow(),
    )
    db.add(customer)
    db.flush()
    # back-fill: link unlinked shipments addressed to this email
    db.query(Shipment).filter(
        Shipment.customer_id.is_(None), func.lower(Shipment.receiver_email) == email
    ).update({Shipment.customer_id: customer.id}, synchronize_session=False)
    db.commit()

    set_session_cookie(response, customer.id)
    background.add_task(send_welcome, customer)
    return {"ok": True, "customer": customer_dict(customer)}


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if login_limiter.blocked(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please wait a few minutes.")
    email = payload.email.strip().lower()
    customer = db.query(Customer).filter(func.lower(Customer.email) == email).first()
    if not customer or not verify_password(payload.password, customer.password_hash):
        login_limiter.hit(ip)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    login_limiter.reset(ip)
    customer.last_login = utcnow()
    db.commit()
    set_session_cookie(response, customer.id)
    return {"ok": True, "customer": customer_dict(customer)}


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if not customer:
        return {"authenticated": False}
    return {"authenticated": True, "customer": customer_dict(customer)}


@router.get("/shipments")
def my_shipments(customer: Customer = Depends(require_customer), db: Session = Depends(get_db)):
    return customer_shipments(db, customer)


@router.post("/shipments/link")
def link_shipment(payload: TrackingNumberIn, customer: Customer = Depends(require_customer), db: Session = Depends(get_db)):
    shipment = find_shipment(db, payload.tracking_number)
    if not shipment:
        raise HTTPException(status_code=404, detail="Tracking number not found")
    if is_owner(shipment, customer):
        return {"ok": True, "source": "owned", "tracking_number": shipment.tracking_number}
    exists = (
        db.query(ShipmentWatch.id)
        .filter(ShipmentWatch.customer_id == customer.id, ShipmentWatch.shipment_id == shipment.id)
        .first()
    )
    if not exists:
        db.add(ShipmentWatch(customer_id=customer.id, shipment_id=shipment.id))
        db.commit()
    return {"ok": True, "source": "followed", "tracking_number": shipment.tracking_number}


@router.post("/shipments/unfollow")
def unfollow_shipment(payload: TrackingNumberIn, customer: Customer = Depends(require_customer), db: Session = Depends(get_db)):
    shipment = find_shipment(db, payload.tracking_number)
    if not shipment:
        raise HTTPException(status_code=404, detail="Tracking number not found")
    db.query(ShipmentWatch).filter(
        ShipmentWatch.customer_id == customer.id, ShipmentWatch.shipment_id == shipment.id
    ).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}


@router.post("/shipments/{shipment_id}/notify")
def set_notify(shipment_id: int, payload: NotifyIn, customer: Customer = Depends(require_customer), db: Session = Depends(get_db)):
    shipment = db.get(Shipment, shipment_id)
    if not shipment or not is_owner(shipment, customer):
        raise HTTPException(status_code=404, detail="Shipment not found")
    shipment.notify_email = 1 if payload.notify_email else 0
    db.commit()
    return {"ok": True, "notify_email": bool(shipment.notify_email)}

"""Demo data on first boot (only when SEED_DEMO=1 and there are no shipments).

All coordinates are hard-coded so maps render without any geocoding/routing calls.
"""
import json
from datetime import timedelta

from .auth import hash_password
from .config import SEED_DEMO
from .database import SessionLocal
from .models import Customer, Shipment, ShipmentWatch, TrackingEvent, utcnow
from .utils import generate_tracking_number

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo1234"
DEMO_OTHER_RECEIVER = "jordan.lee@example.org"
# receivers of the seeded demo shipments (used to show demo hints in the UI)
DEMO_RECEIVERS = (DEMO_EMAIL, DEMO_OTHER_RECEIVER)

# London -> Folkestone -> Calais -> Antwerp -> Amsterdam -> Hanover -> Berlin (approximate road line)
LONDON_BERLIN_ROUTE = [
    [51.5074, -0.1278],
    [51.4416, 0.1530],
    [51.2724, 0.5229],
    [51.0814, 1.1695],
    [50.9513, 1.8587],
    [51.0344, 2.3768],
    [51.2093, 3.2247],
    [51.2194, 4.4025],
    [51.5719, 4.7683],
    [51.9244, 4.4777],
    [52.3676, 4.9041],
    [52.1561, 5.3878],
    [52.2112, 5.9699],
    [52.2799, 8.0472],
    [52.3759, 9.7320],
    [52.1205, 11.6276],
    [52.4009, 13.0591],
    [52.5200, 13.4050],
]


def _shipment(db, **kw) -> Shipment:
    s = Shipment(tracking_number=generate_tracking_number(db), **kw)
    db.add(s)
    db.flush()
    return s


def _events(db, shipment, rows):
    """rows: (status, location, lat, lng, notes, timestamp)"""
    for status, loc, lat, lng, notes, ts in rows:
        db.add(
            TrackingEvent(
                shipment_id=shipment.id,
                status=status,
                location_name=loc,
                lat=lat,
                lng=lng,
                notes=notes,
                updated_by="Operations",
                timestamp=ts,
            )
        )
    last = rows[-1]
    shipment.current_status = last[0]
    located = [r for r in rows if r[2] is not None]
    if located:
        shipment.current_lat, shipment.current_lng = located[-1][2], located[-1][3]


def seed_if_empty() -> None:
    if not SEED_DEMO:
        return
    db = SessionLocal()
    try:
        if db.query(Shipment.id).first():
            return
        now = utcnow()

        demo = db.query(Customer).filter(Customer.email == DEMO_EMAIL).first()
        if not demo:
            demo = Customer(
                first_name="Demo",
                last_name="Customer",
                email=DEMO_EMAIL,
                phone="+1 555 0100",
                password_hash=hash_password(DEMO_PASSWORD),
            )
            db.add(demo)
            db.flush()

        # 1) Delivered — Lisbon to Paris
        d0 = now - timedelta(days=9)
        s1 = _shipment(
            db,
            sender_name="Atelier Azul Ceramics",
            sender_address="Rua Augusta 120, Lisbon, Portugal",
            receiver_name="Demo Customer",
            receiver_email=DEMO_EMAIL,
            receiver_phone="+1 555 0100",
            receiver_address="18 Rue de Rivoli, 75004 Paris, France",
            origin="Lisbon, Portugal",
            destination="Paris, France",
            package_type="Parcel",
            weight="4.2 kg",
            service_type="Standard",
            estimated_delivery=(now - timedelta(days=3)).strftime("%b %d, %Y"),
            carrier="Road Partner Network",
            carrier_reference="RPN-77120",
            shipment_mode="Ground / Road",
            product="Hand-painted ceramic tableware",
            qty="1",
            piece_type="Box",
            payment_mode="Prepaid",
            total_freight="€38.00",
            departure_time="09:30",
            pickup_date=d0.strftime("%Y-%m-%d"),
            pickup_time="09:00",
            length_cm="45",
            width_cm="35",
            height_cm="30",
            comments="Fragile — handle with care.",
            customer_id=demo.id,
            created_at=d0,
        )
        _events(
            db,
            s1,
            [
                ("Pending", "Lisbon, Portugal", 38.7223, -9.1393, "Shipment created", d0),
                ("Picked Up", "Lisbon, Portugal", 38.7223, -9.1393, "Collected from sender", d0 + timedelta(hours=5)),
                ("Departed Hub", "Lisbon Sorting Centre", 38.7569, -9.1180, None, d0 + timedelta(hours=14)),
                ("Arrived at Hub", "Madrid, Spain", 40.4168, -3.7038, "Arrived at regional hub", d0 + timedelta(days=1, hours=6)),
                ("In Transit", "Bordeaux, France", 44.8378, -0.5792, None, d0 + timedelta(days=3, hours=2)),
                ("Arrived at Hub", "Paris, France", 48.8566, 2.3522, None, d0 + timedelta(days=4, hours=8)),
                ("Out for Delivery", "Paris, France", 48.8566, 2.3522, "With local courier", d0 + timedelta(days=5, hours=7)),
                ("Delivered", "Paris, France", 48.8566, 2.3522, "Signed for by recipient", d0 + timedelta(days=5, hours=13)),
            ],
        )

        # 2) In Transit — New York to San Francisco (checkpoints only, no road route)
        d1 = now - timedelta(days=3, hours=4)
        s2 = _shipment(
            db,
            sender_name="Northwind Electronics",
            sender_address="350 5th Ave, New York, NY",
            receiver_name="Jordan Lee",
            receiver_email=DEMO_OTHER_RECEIVER,
            receiver_address="500 Market St, San Francisco, CA",
            origin="New York, USA",
            destination="San Francisco, USA",
            package_type="Parcel",
            weight="2.8 kg",
            service_type="Express",
            estimated_delivery=(now + timedelta(days=2)).strftime("%b %d, %Y"),
            carrier="Air & Road Linehaul",
            carrier_reference="ARL-55301",
            shipment_mode="Express",
            product="Laptop accessories",
            qty="2",
            piece_type="Box",
            payment_mode="Card",
            total_freight="$64.50",
            pickup_date=d1.strftime("%Y-%m-%d"),
            pickup_time="14:00",
            length_cm="40",
            width_cm="30",
            height_cm="12",
            created_at=d1,
        )
        _events(
            db,
            s2,
            [
                ("Pending", "New York, USA", 40.7128, -74.0060, "Shipment created", d1),
                ("Picked Up", "New York, USA", 40.7128, -74.0060, None, d1 + timedelta(hours=3)),
                ("Departed Hub", "Newark, NJ, USA", 40.7357, -74.1724, None, d1 + timedelta(hours=11)),
                ("Arrived at Hub", "Chicago, IL, USA", 41.8781, -87.6298, None, d1 + timedelta(days=1, hours=4)),
                ("Departed Hub", "Chicago, IL, USA", 41.8781, -87.6298, None, d1 + timedelta(days=1, hours=16)),
                ("In Transit", "Denver, CO, USA", 39.7392, -104.9903, "On schedule", d1 + timedelta(days=2, hours=20)),
            ],
        )
        db.add(ShipmentWatch(customer_id=demo.id, shipment_id=s2.id))

        # 3) Animated journey — London to Berlin, currently moving
        d2 = now - timedelta(hours=30)
        start = now - timedelta(hours=5)
        end = now + timedelta(hours=11)
        s3 = _shipment(
            db,
            sender_name="Kingsway Print Studio",
            sender_address="22 Shoreditch High St, London, UK",
            receiver_name="Demo Customer",
            receiver_email=DEMO_EMAIL,
            receiver_address="Friedrichstraße 68, 10117 Berlin, Germany",
            origin="London, UK",
            destination="Berlin, Germany",
            package_type="Freight",
            weight="38 kg",
            service_type="Standard",
            estimated_delivery=end.strftime("%b %d, %Y %H:%M UTC"),
            carrier="Road Partner Network",
            carrier_reference="RPN-90412",
            shipment_mode="Ground / Road",
            product="Exhibition prints and frames",
            qty="3",
            piece_type="Crate",
            payment_mode="Bank transfer",
            total_freight="£210.00",
            departure_time=start.strftime("%H:%M UTC"),
            pickup_date=d2.strftime("%Y-%m-%d"),
            pickup_time="10:00",
            length_cm="120",
            width_cm="80",
            height_cm="40",
            comments="Deliver to loading bay, weekdays 08:00–17:00.",
            customer_id=demo.id,
            created_at=d2,
            journey_origin="London, UK",
            journey_destination="Berlin, Germany",
            journey_waypoints=json.dumps(["Amsterdam, Netherlands"]),
            route_path=json.dumps(LONDON_BERLIN_ROUTE),
            journey_start=start,
            journey_end=end,
            journey_state="moving",
        )
        _events(
            db,
            s3,
            [
                ("Pending", "London, UK", 51.5074, -0.1278, "Shipment created", d2),
                ("Picked Up", "London, UK", 51.5074, -0.1278, "Collected from sender", start - timedelta(hours=3)),
                ("In Transit", "London, UK", 51.5074, -0.1278, "Departed on scheduled road route", start),
            ],
        )
        db.commit()
        print(f"[seed] demo customer: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"[seed] delivered:        {s1.tracking_number}")
        print(f"[seed] in transit:       {s2.tracking_number}")
        print(f"[seed] moving journey:   {s3.tracking_number}")
    finally:
        db.close()

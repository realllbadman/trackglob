import logging
import os

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.orm import declarative_base, sessionmaker  # noqa: E402

log = logging.getLogger("tracking.db")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tracking.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns that may be missing from databases created by older versions of the app.
# Only additive changes; SQLite can ADD COLUMN but not much else.
WANTED_COLUMNS = {
    "customers": {
        "phone": "TEXT",
        "last_login": "DATETIME",
    },
    "shipments": {
        "customer_id": "INTEGER",
        "sender_address": "TEXT",
        "receiver_phone": "TEXT",
        "receiver_address": "TEXT",
        "origin": "TEXT",
        "destination": "TEXT",
        "package_type": "TEXT",
        "weight": "TEXT",
        "service_type": "TEXT",
        "current_lat": "FLOAT",
        "current_lng": "FLOAT",
        "estimated_delivery": "TEXT",
        "notify_email": "INTEGER DEFAULT 1",
        "carrier": "TEXT",
        "carrier_reference": "TEXT",
        "shipment_mode": "TEXT",
        "product": "TEXT",
        "qty": "TEXT",
        "piece_type": "TEXT",
        "payment_mode": "TEXT",
        "total_freight": "TEXT",
        "departure_time": "TEXT",
        "pickup_date": "TEXT",
        "pickup_time": "TEXT",
        "length_cm": "TEXT",
        "width_cm": "TEXT",
        "height_cm": "TEXT",
        "comments": "TEXT",
        "journey_origin": "TEXT",
        "journey_destination": "TEXT",
        "journey_waypoints": "TEXT",
        "route_path": "TEXT",
        "journey_start": "DATETIME",
        "journey_end": "DATETIME",
        "journey_paused_at": "DATETIME",
        "journey_paused_frac": "FLOAT",
        "journey_state": "TEXT DEFAULT 'not_started'",
    },
    "tracking_events": {
        "location_name": "TEXT",
        "lat": "FLOAT",
        "lng": "FLOAT",
        "notes": "TEXT",
        "updated_by": "TEXT",
    },
}


def ensure_columns() -> None:
    """Idempotent lightweight migration: add any missing columns."""
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in WANTED_COLUMNS.items():
            if table not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, coltype in cols.items():
                if name not in have:
                    log.info("ensure_columns: adding %s.%s", table, name)
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {coltype}'))

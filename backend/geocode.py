"""Geocoding via Nominatim (OpenStreetMap) with a memory + DB cache and a polite rate limit."""
import logging
import os
import threading
import time
from typing import Dict, Optional, Tuple

import httpx

from .database import SessionLocal
from .models import GeocodeCache

log = logging.getLogger("tracking.geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_MIN_INTERVAL = 1.1  # Nominatim usage policy: max 1 request/second

_memory: Dict[str, Optional[Tuple[float, float]]] = {}
_lock = threading.Lock()
_last_call = 0.0


def _user_agent() -> str:
    name = os.getenv("BUSINESS_NAME") or "Parcel"
    email = os.getenv("OWNER_EMAIL") or "admin@localhost"
    return f"{name} tracking ({email})"


def _db_lookup(key: str):
    """Returns (found_row, value). found_row False = real miss (never looked up)."""
    db = SessionLocal()
    try:
        row = db.query(GeocodeCache).filter(GeocodeCache.address == key).first()
        if not row:
            return False, None
        if row.lat is None or row.lng is None:
            return True, None
        return True, (row.lat, row.lng)
    finally:
        db.close()


def _db_store(key: str, value: Optional[Tuple[float, float]]) -> None:
    db = SessionLocal()
    try:
        if db.query(GeocodeCache.id).filter(GeocodeCache.address == key).first():
            return
        db.add(GeocodeCache(address=key, lat=value[0] if value else None, lng=value[1] if value else None))
        db.commit()
    except Exception as exc:  # unique race between workers etc.
        db.rollback()
        log.warning("geocode cache store failed for %r: %s", key, exc)
    finally:
        db.close()


def geocode(address: Optional[str]) -> Optional[Tuple[float, float]]:
    global _last_call
    if not address or not address.strip():
        return None
    key = address.strip().lower()[:500]

    if key in _memory:
        return _memory[key]

    found, value = _db_lookup(key)
    if found:
        _memory[key] = value
        return value

    with _lock:
        if key in _memory:  # another thread got there first
            return _memory[key]
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        result: Optional[Tuple[float, float]] = None
        try:
            resp = httpx.get(
                NOMINATIM_URL,
                params={"q": address.strip(), "format": "json", "limit": 1},
                headers={"User-Agent": _user_agent()},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data:
                result = (float(data[0]["lat"]), float(data[0]["lon"]))
        except Exception as exc:
            log.warning("geocode failed for %r: %s", address, exc)
            _last_call = time.monotonic()
            return None  # network error: don't cache, try again next time
        _last_call = time.monotonic()
        _memory[key] = result
    _db_store(key, result)
    return result

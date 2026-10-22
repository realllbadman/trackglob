"""Road routing via the public OSRM demo server, with a straight-line fallback."""
import logging
from typing import List

import httpx

from .geocode import geocode

log = logging.getLogger("tracking.routing")

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/"


def get_road_route(points: List[str]) -> List[List[float]]:
    coords: List[List[float]] = []
    for p in points:
        if p and p.strip():
            hit = geocode(p)
            if hit:
                coords.append([hit[0], hit[1]])
    if len(coords) < 2:
        return coords

    try:
        path = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in coords)
        resp = httpx.get(
            OSRM_URL + path,
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": "parcel-tracking"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        geometry = data["routes"][0]["geometry"]["coordinates"]
        route = [[round(lat, 6), round(lng, 6)] for lng, lat in geometry]
        if len(route) >= 2:
            return route
    except Exception as exc:
        log.warning("OSRM routing failed, using straight line: %s", exc)
    return coords

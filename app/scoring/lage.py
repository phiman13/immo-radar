from __future__ import annotations

import math

from app.config import settings

# Approximate centers of Tutzing Ortsteile (lat, lon).
ORTSTEILE: dict[str, tuple[float, float]] = {
    "Tutzing-Zentrum": (47.9095, 11.2783),
    "Garatshausen": (47.9234, 11.2876),
    "Kampberg": (47.8989, 11.2682),
    "Oberzeismering": (47.9012, 11.2541),
    "Unterzeismering": (47.9054, 11.2620),
    "Diemendorf": (47.8859, 11.2998),
    "Deixlfurt": (47.8943, 11.2497),
    "Traubing": (47.9357, 11.2420),
    "Kerschlach": (47.8612, 11.2387),
}

# S6 Tutzing station (approx).
S6_TUTZING = (47.9088, 11.2812)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    R = 6371.0
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def classify_ortsteil(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    nearest = min(ORTSTEILE.items(), key=lambda kv: haversine_km((lat, lon), kv[1]))
    return nearest[0]


def in_search_area(
    lat: float | None,
    lon: float | None,
    locations: list[dict] | None = None,
) -> bool:
    if lat is None or lon is None:
        return True  # don't filter unknown locations — better than dropping good leads
    if not locations:
        # legacy: use single-location settings
        center = (settings.search_center_lat, settings.search_center_lon)
        return haversine_km(center, (lat, lon)) <= settings.search_radius_km
    return any(haversine_km((loc["lat"], loc["lon"]), (lat, lon)) <= loc["radius_km"] for loc in locations)


def distance_to_sbahn_km(lat: float | None, lon: float | None) -> float | None:
    if lat is None or lon is None:
        return None
    return round(haversine_km((lat, lon), S6_TUTZING), 2)

"""
Geographic helpers.

Distance between two points drives one of the strongest fraud
signals in the whole system: a card used in Mumbai and then in
Dubai eleven minutes later is physically impossible.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two points, in kilometres.

    "Great-circle" means distance across the curved surface of the
    Earth, not a straight line through it. Straight-line distance
    would understate real travel distance significantly.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def implied_speed_kmh(distance_km: float, seconds_elapsed: float) -> float:
    """
    Speed required to cover a distance in a given time.

    The core of the "geo-impossible" fraud signal. Anything above
    roughly 900 km/h means the cardholder would have to be on a
    commercial aircraft — and above ~1200 km/h is impossible.

    Returns infinity when no time has passed, which correctly
    represents "two places at once".
    """
    if seconds_elapsed <= 0:
        return float("inf")
    hours = seconds_elapsed / 3600.0
    return distance_km / hours


def jitter_coordinate(
    lat: float, lon: float, radius_km: float, rng
) -> tuple[float, float]:
    """
    Produce a random point within radius_km of the given coordinate.

    Used so that every transaction in Mumbai doesn't land on the
    exact same latitude and longitude, which would be an obvious
    giveaway that the data is synthetic.

    Args:
        rng: a numpy Generator, passed in so results stay reproducible.
    """
    # Convert km to degrees. 1 degree of latitude is ~111 km everywhere.
    # Longitude degrees shrink as you move away from the equator, hence
    # the cos(latitude) correction.
    radius_deg_lat = radius_km / 111.0
    radius_deg_lon = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))

    # Uniform sampling inside a circle requires sqrt on the radius,
    # otherwise points cluster toward the centre.
    angle = rng.uniform(0, 2 * math.pi)
    distance = math.sqrt(rng.uniform(0, 1))

    return (
        lat + distance * radius_deg_lat * math.sin(angle),
        lon + distance * radius_deg_lon * math.cos(angle),
    )
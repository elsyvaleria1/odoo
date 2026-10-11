import math

EARTH_RADIUS_KM = 6371.0


def has_fix(latitude, longitude) -> bool:
    return latitude != 0.0 or longitude != 0.0


def haversine_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(haversine))


def haversine_m(lat1, lon1, lat2, lon2):
    return haversine_km(lat1, lon1, lat2, lon2) * 1000.0


import math
from datetime import timedelta

KM_PER_LITRE = 9.0
EARTH_RADIUS_M = 6_371_000.0


def _distance_m(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def make_gps_device(env, vehicle, receiver_key, tank_litres=55.0):
    profile = env["device.profile"].search(
        [("name", "=", "Simulated Teltonika")], limit=1
    ) or env["device.profile"].create(
        {
            "name": "Simulated Teltonika",
            "gps_tracking_enabled": True,
            "gps_protocol": "teltonika",
            "reports_odometer": True,
            "odometer_source": "gps",
            "fuel_reports_percentage": True,
            "fuel_source": "percentage",
            "reports_ignition": True,
        }
    )
    device = env["device.device"].create(
        {
            "name": f"GPS {vehicle.name}",
            "identifier": receiver_key,
            "auth_type": "none",
            "comm_protocol": "https",
            "processing_mode": "sync",
            "is_gps_device": True,
            "gps_tracking_enabled": True,
            "gps_receiver_key": receiver_key,
            "config_id": profile.id,
            "fuel_tank_capacity": tank_litres,
        }
    )
    vehicle.gps_device_id = device
    return device


class RouteSimulator:
    def __init__(
        self,
        env,
        device,
        start,
        latitude,
        longitude,
        odometer_km,
        fuel_percent,
        step=timedelta(seconds=30),
        tank_litres=55.0,
    ):
        self.env = env
        self.device = device
        self.now = start
        self.latitude = latitude
        self.longitude = longitude
        self.odometer_km = odometer_km
        self.fuel_percent = fuel_percent
        self.step = step
        self.tank_litres = tank_litres
        self.logs = env["device.data.log.gps"]

    def _report(self, speed, ignition, event="0"):
        payload = {
            "14": self.device.gps_receiver_key,
            "ts": int(self.now.timestamp() * 1000),
            "latlng": f"{self.latitude:.7f},{self.longitude:.7f}",
            "sp": round(speed),
            "sat": 11,
            "alt": 2600,
            "ang": 0,
            "evt": event,
            "239": int(ignition),
            "240": int(speed > 0),
            "87": int(self.odometer_km * 1000),
            "89": round(self.fuel_percent),
            "182": 0.8,
        }
        processor = self.env["device.gps.data.processor"].sudo()
        stats = {"quality_checks_passed": 0, "quality_checks_failed": 0}
        valid, message, _device, vals = processor._process_gps_data(
            payload, stats, device=self.device
        )
        if not valid:
            raise ValueError(f"Simulated reading refused: {message}")
        vals["source"] = "webhook"
        self.logs |= self.env["device.data.log.gps"].sudo().create_gps_log(vals)

    def drive_to(self, latitude, longitude, speed=45.0, harsh_at=None, towed=False):
        distance = _distance_m(self.latitude, self.longitude, latitude, longitude)
        seconds = distance / (speed / 3.6)
        steps = max(1, math.ceil(seconds / self.step.total_seconds()))
        lat0, lon0 = self.latitude, self.longitude
        for index in range(1, steps + 1):
            fraction = index / steps
            new_lat = lat0 + (latitude - lat0) * fraction
            new_lon = lon0 + (longitude - lon0) * fraction
            km = _distance_m(self.latitude, self.longitude, new_lat, new_lon) / 1000
            self.latitude, self.longitude = new_lat, new_lon
            self.odometer_km += km
            if not towed:
                self.fuel_percent -= km / KM_PER_LITRE / self.tank_litres * 100
            self.now += self.step
            harsh = harsh_at is not None and index == max(1, round(steps * harsh_at))
            self._report(speed, not towed, event="253" if harsh else "0")

    def dwell(self, minutes, ignition=False):
        for _ in range(max(1, round(minutes * 60 / self.step.total_seconds()))):
            self.now += self.step
            self._report(0.0, ignition)

    def refuel(self, litres):
        self.fuel_percent = min(
            100.0, self.fuel_percent + litres / self.tank_litres * 100
        )
        self.now += self.step
        self._report(0.0, False)

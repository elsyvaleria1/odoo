#!/usr/bin/env python3

import argparse
import contextlib
import csv
import json
import math
import os
import pathlib
import random
import time
from datetime import UTC, datetime, timedelta

import requests


class GPSSimulator:
    def __init__(
        self,
        base_url=None,
        receiver_key=None,
        start_lat=40.7128,
        start_lon=-74.0060,
        token=None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/") if base_url else None
        self.receiver_key = receiver_key or f"SIM{random.randint(100000000, 999999999)}"
        self.current_lat = start_lat
        self.current_lon = start_lon
        self.current_speed = 0
        self.current_heading = random.randint(0, 360)
        self.ignition = True
        self.fuel_level = random.randint(50, 100)
        self.battery_level = random.randint(80, 100)
        self.odometer = random.randint(10000, 50000)

    def simulate_movement(self) -> None:
        speed_change = random.uniform(-5, 5)
        self.current_speed = max(0, min(120, self.current_speed + speed_change))

        heading_change = random.uniform(-10, 10)
        self.current_heading = (self.current_heading + heading_change) % 360

        if self.current_speed > 0:
            speed_ms = self.current_speed / 3.6

            distance = speed_ms / 111000

            heading_rad = math.radians(self.current_heading)
            self.current_lat += distance * math.cos(heading_rad)
            self.current_lon += distance * math.sin(heading_rad)

            self.odometer += speed_ms / 1000

        if self.ignition and self.current_speed > 0:
            self.fuel_level = max(0, self.fuel_level - random.uniform(0, 0.1))

        self.battery_level = max(0, self.battery_level - random.uniform(0, 0.05))

    def generate_gps_data(self, timestamp=None) -> dict:
        self.simulate_movement()

        hdop_raw = random.randint(8, 25)
        accuracy = round((hdop_raw / 10.0) * 4.0, 1)

        return {
            "receiver_key": self.receiver_key,
            "data": {
                "latitude": round(self.current_lat, 7),
                "longitude": round(self.current_lon, 7),
                "timestamp": timestamp or datetime.now(UTC).isoformat(),
                "speed": round(self.current_speed, 1),
                "altitude": random.randint(50, 150),
                "satellites": random.randint(6, 12),
                "gnss_hdop": hdop_raw,
                "accuracy": accuracy,
                "heading": round(self.current_heading, 1),
                "battery": round(self.battery_level, 1),
                "ignition": self.ignition,
                "movement": self.current_speed > 0,
                "odometer": round(self.odometer, 1),
                "fuel_level": round(self.fuel_level, 1),
                "engine_temperature": (random.randint(70, 95) if self.ignition else 20),
                "engine_speed_rpm": (
                    random.randint(800, 3000)
                    if self.ignition and self.current_speed > 0
                    else 0
                ),
                "battery_voltage": round(random.uniform(12.0, 14.5), 1),
                "external_voltage": (
                    round(random.uniform(13.0, 14.5), 1) if self.ignition else 0
                ),
                "gsm_signal": random.randint(3, 5),
            },
        }

    @staticmethod
    def _prepare_webhook_payload(data):
        point = data["data"]
        timestamp = datetime.fromisoformat(point["timestamp"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return {
            "state": {
                "reported": {
                    "14": data["receiver_key"],
                    "latlng": f"{point['latitude']},{point['longitude']}",
                    "ts": int(timestamp.timestamp() * 1000),
                    "sp": point["speed"],
                    "alt": point["altitude"],
                    "sat": point["satellites"],
                    "ang": point["heading"],
                    "182": point["gnss_hdop"],
                    "239": int(point["ignition"]),
                    "240": int(point["movement"]),
                    "87": point["odometer"] * 1000,
                    "89": point["fuel_level"],
                    "113": point["battery"],
                    "115": point["engine_temperature"] * 10,
                    "85": point["engine_speed_rpm"],
                    "67": point["battery_voltage"] * 1000,
                    "66": point["external_voltage"] * 1000,
                    "21": point["gsm_signal"],
                }
            }
        }

    def send_data(self, data) -> bool:
        if not self.base_url:
            return False

        url = f"{self.base_url}/remote/gps/webhook"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            response = requests.post(  # noqa: E8518 -- a standalone script run outside the server, with no ir.egress to reach
                url,
                json=self._prepare_webhook_payload(data),
                headers=headers,
                timeout=30,
            )
            return response.status_code == 200 and response.content == b"\x01"
        except requests.RequestException, ValueError:
            return False

    def simulate_route(self, duration_minutes=10, interval_seconds=30) -> None:
        if not self.base_url:
            return

        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        update_count = 0

        self.current_speed = random.uniform(30, 60)

        while time.time() < end_time:
            data = self.generate_gps_data()

            self.send_data(data)

            update_count += 1

            if random.random() < 0.1:
                self.current_speed = 0
            elif random.random() < 0.1 and self.current_speed == 0:
                self.current_speed = random.uniform(20, 50)

            time.sleep(interval_seconds)


def get_heading(pos1, pos2):
    lat1, lon1 = pos1
    lat2, lon2 = pos2

    dlon = lon2 - lon1
    x = math.cos(math.radians(lat2)) * math.sin(math.radians(dlon))
    y = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(
        math.radians(lat1)
    ) * math.cos(math.radians(lat2)) * math.cos(math.radians(dlon))

    heading = math.degrees(math.atan2(x, y))
    return (heading + 360) % 360


def generate_demo_tracking_data(hours=24, points_per_hour=2):
    routes = {
        "truck_01": {
            "receiver_key": "352625100123001",
            "start": (40.7128, -74.0060),
            "waypoints": [
                (40.7200, -74.0000),
                (40.7300, -73.9950),
                (40.7400, -73.9900),
                (40.7500, -73.9870),
                (40.7580, -73.9855),
            ],
            "speed_range": (30, 60),
            "stops": [5],
        },
        "truck_02": {
            "receiver_key": "352625100123002",
            "start": (40.7580, -73.9855),
            "waypoints": [],
            "speed_range": (0, 0),
            "stops": [],
        },
        "van_01": {
            "receiver_key": "352625100123003",
            "start": (40.7128, -74.0060),
            "waypoints": [
                (40.7000, -74.0100),
                (40.6950, -74.0200),
                (40.6900, -74.0300),
                (40.6892, -74.0445),
            ],
            "speed_range": (40, 80),
            "stops": [],
        },
        "asset_01": {
            "receiver_key": "352625100123004",
            "start": (40.7489, -73.9680),
            "waypoints": [],
            "speed_range": (0, 0),
            "stops": [],
        },
    }

    tracking_points = []
    base_time = datetime.now(UTC) - timedelta(hours=hours)

    for device_name, route in routes.items():
        device_id = f"demo_gps_device_{device_name}"
        simulator = GPSSimulator(
            receiver_key=route["receiver_key"],
            start_lat=route["start"][0],
            start_lon=route["start"][1],
        )

        if route["waypoints"]:
            total_points = hours * points_per_hour
            points_per_segment = total_points // (len(route["waypoints"]) + 1)

            current_pos = route["start"]
            current_time = base_time

            for i, waypoint in enumerate(route["waypoints"] + [route["waypoints"][-1]]):
                for j in range(points_per_segment):
                    progress = j / points_per_segment
                    lat = current_pos[0] + (waypoint[0] - current_pos[0]) * progress
                    lon = current_pos[1] + (waypoint[1] - current_pos[1]) * progress

                    lat += random.uniform(-0.0005, 0.0005)
                    lon += random.uniform(-0.0005, 0.0005)

                    simulator.current_lat = lat
                    simulator.current_lon = lon

                    is_stopped = i in route["stops"] and j > points_per_segment * 0.8

                    if is_stopped:
                        simulator.current_speed = 0
                        simulator.ignition = False
                    else:
                        simulator.current_speed = random.uniform(*route["speed_range"])
                        simulator.ignition = True
                        simulator.current_heading = get_heading(current_pos, waypoint)

                    point = simulator.generate_gps_data(current_time.isoformat())
                    point["device_id"] = device_id
                    tracking_points.append(point)

                    current_time += timedelta(hours=1 / points_per_hour)

                current_pos = waypoint

        else:
            for hour in range(hours * points_per_hour):
                simulator.current_speed = 0
                simulator.ignition = False

                point = simulator.generate_gps_data(
                    (base_time + timedelta(hours=hour / points_per_hour)).isoformat()
                )
                point["device_id"] = device_id
                tracking_points.append(point)

    return tracking_points


def generate_xml_records(tracking_points):
    xml_records = []

    for i, point in enumerate(tracking_points):
        record_id = f"demo_tracking_point_{i:04d}"

        xml_record = f"""
        <record id="{record_id}" model="device.data.log.gps">
            <field name="iot_device_id" ref="{point["device_id"]}"/>
            <field name="timestamp">{point["data"]["timestamp"]}</field>
            <field name="latitude">{point["data"]["latitude"]}</field>
            <field name="longitude">{point["data"]["longitude"]}</field>
            <field name="altitude">{point["data"]["altitude"]}</field>
            <field name="speed">{point["data"]["speed"]}</field>
            <field name="satellites">{point["data"]["satellites"]}</field>
            <field name="gnss_hdop">{point["data"]["gnss_hdop"] / 10.0}</field>
            <field name="accuracy">{point["data"]["accuracy"]}</field>
            <field name="heading">{point["data"]["heading"]}</field>
            <field name="battery_level">{point["data"]["battery"]}</field>
            <field name="ignition">{point["data"]["ignition"]}</field>
            <field name="movement">{point["data"]["movement"]}</field>
            <field name="odometer">{point["data"]["odometer"]}</field>
            <field name="fuel_level">{point["data"]["fuel_level"]}</field>
            <field name="engine_temperature">{point["data"]["engine_temperature"]}</field>
            <field name="engine_speed_rpm">{point["data"]["engine_speed_rpm"]}</field>
        </record>"""

        xml_records.append(xml_record)

    return xml_records


def generate_csv_sample(output_file="sample_gps_data.csv"):
    headers = [
        "receiver_key",
        "timestamp",
        "latitude",
        "longitude",
        "speed",
        "altitude",
        "satellites",
        "gnss_hdop",
        "accuracy",
        "heading",
        "ignition",
        "movement",
        "battery",
        "fuel_level",
        "odometer",
    ]

    with pathlib.Path(output_file).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()

        simulator = GPSSimulator(receiver_key="123456789012345")
        base_time = datetime.now(UTC)

        for i in range(100):
            data = simulator.generate_gps_data(
                (base_time + timedelta(minutes=i)).isoformat()
            )

            row = {
                "receiver_key": data["receiver_key"],
                "timestamp": data["data"]["timestamp"],
                "latitude": data["data"]["latitude"],
                "longitude": data["data"]["longitude"],
                "speed": data["data"]["speed"],
                "altitude": data["data"]["altitude"],
                "satellites": data["data"]["satellites"],
                "gnss_hdop": data["data"]["gnss_hdop"] / 10.0,
                "accuracy": data["data"]["accuracy"],
                "heading": data["data"]["heading"],
                "ignition": str(data["data"]["ignition"]).lower(),
                "movement": str(data["data"]["movement"]).lower(),
                "battery": data["data"]["battery"],
                "fuel_level": data["data"]["fuel_level"],
                "odometer": data["data"]["odometer"],
            }
            writer.writerow(row)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="GPS Simulator and Demo Data Generator"
    )

    subparsers = parser.add_subparsers(dest="mode", help="Operation mode")

    sim_parser = subparsers.add_parser("simulate", help="Real-time GPS simulation")
    sim_parser.add_argument(
        "--url",
        default="http://localhost:8069",
        help="Odoo server URL (default: http://localhost:8069)",
    )
    sim_parser.add_argument(
        "--receiver-key",
        "--imei",
        dest="receiver_key",
        help="Configured GPS receiver key (field 14, not hardware IMEI)",
    )
    sim_parser.add_argument(
        "--token-env",
        default="ODOO_GPS_TOKEN",
        help="Environment variable containing the receiver bearer token",
    )
    sim_parser.add_argument(
        "--lat",
        type=float,
        default=40.7128,
        help="Starting latitude (default: 40.7128)",
    )
    sim_parser.add_argument(
        "--lon",
        type=float,
        default=-74.0060,
        help="Starting longitude (default: -74.0060)",
    )
    sim_parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Simulation duration in minutes (default: 10)",
    )
    sim_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Update interval in seconds (default: 30)",
    )

    demo_parser = subparsers.add_parser("generate-demo", help="Generate demo data")
    demo_parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Hours of data to generate (default: 24)",
    )
    demo_parser.add_argument(
        "--points-per-hour",
        type=int,
        default=2,
        help="Data points per hour (default: 2)",
    )
    demo_parser.add_argument(
        "--format",
        choices=["xml", "json", "both"],
        default="both",
        help="Output format (default: both)",
    )

    csv_parser = subparsers.add_parser("generate-csv", help="Generate sample CSV")
    csv_parser.add_argument(
        "--output",
        default="sample_gps_data.csv",
        help="Output file name (default: sample_gps_data.csv)",
    )

    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        return

    if args.mode == "simulate":
        simulator = GPSSimulator(
            base_url=args.url,
            token=os.environ.get(args.token_env),
            receiver_key=args.receiver_key,
            start_lat=args.lat,
            start_lon=args.lon,
        )
        with contextlib.suppress(KeyboardInterrupt):
            simulator.simulate_route(args.duration, args.interval)

    elif args.mode == "generate-demo":
        points = generate_demo_tracking_data(args.hours, args.points_per_hour)

        if args.format in ["json", "both"]:
            with pathlib.Path("demo_tracking_points.json").open(
                "w", encoding="utf-8"
            ) as f:
                json.dump(points, f, indent=2)

        if args.format in ["xml", "both"]:
            xml_records = generate_xml_records(points)
            xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">
        <!-- Demo Tracking Points Generated -->
        {"".join(xml_records)}
    </data>
</odoo>"""

            pathlib.Path("demo_tracking_points.xml").write_text(
                xml_content, encoding="utf-8"
            )

        device_counts = {}
        for point in points:
            device = point["device_id"]
            device_counts[device] = device_counts.get(device, 0) + 1

    elif args.mode == "generate-csv":
        generate_csv_sample(args.output)


if __name__ == "__main__":
    main()

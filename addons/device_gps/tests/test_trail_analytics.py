from datetime import datetime, timedelta

from odoo.tests import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase

_START = datetime(2026, 8, 1, 6, 0, 0)


@tagged("post_install", "-at_install")
class TestTrailAnalytics(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gps = cls.env["device.data.log.gps"]

    def _point(self, minutes, **overrides):
        point = {
            "device_id": 1,
            "timestamp": _START + timedelta(minutes=minutes),
            "latitude": 0.0,
            "longitude": 0.0,
            "speed": 0.0,
            "real_odometer": 0.0,
            "odometer_valid": True,
            "fuel_level": 0.0,
            "fuel_level_l": 0.0,
            "ignition": False,
            "movement": False,
        }
        point.update(overrides)
        return point

    def test_no_points_yields_nothing(self):
        self.assertEqual(self.gps.trail_analytics([]), {})

    def test_duration_spans_first_to_last(self):
        points = [self._point(0), self._point(90)]
        self.assertAlmostEqual(
            self.gps.trail_analytics(points)["duration_hours"], 1.5, places=3
        )

    def test_driving_idling_and_parked_are_told_apart(self):
        points = [
            self._point(0, ignition=True, movement=True, speed=40),
            self._point(10, ignition=True, movement=True, speed=40),
            self._point(20, ignition=True, movement=False),
            self._point(30, ignition=False),
        ]
        analytics = self.gps.trail_analytics(points)
        self.assertAlmostEqual(analytics["driving_hours"], 10 / 60, places=3)
        self.assertAlmostEqual(analytics["idling_hours"], 10 / 60, places=3)
        self.assertAlmostEqual(analytics["parked_hours"], 10 / 60, places=3)

    def test_unknown_ignition_while_moving_is_driving_like_the_report(self):
        points = [
            self._point(0, ignition=None, movement=True, speed=40),
            self._point(10, ignition=None, movement=True, speed=40),
        ]
        analytics = self.gps.trail_analytics(points)
        self.assertAlmostEqual(analytics["driving_hours"], 10 / 60, places=3)
        self.assertAlmostEqual(analytics["parked_hours"], 0.0, places=3)

    def test_ignition_off_while_moving_stays_folded_into_parked(self):
        # The daily report calls this state 'coasting'; wizard.device.device.view.trail.result has
        # no coasting column, so the trail deliberately counts it as parked.
        points = [
            self._point(0, ignition=False, movement=True, speed=40),
            self._point(10, ignition=False, movement=True, speed=40),
        ]
        analytics = self.gps.trail_analytics(points)
        self.assertAlmostEqual(analytics["parked_hours"], 10 / 60, places=3)
        self.assertAlmostEqual(analytics["driving_hours"], 0.0, places=3)

    def test_a_signal_gap_is_not_counted_as_time_in_a_state(self):
        points = [
            self._point(0, ignition=True, movement=False),
            self._point(360, ignition=True, movement=False),
        ]
        analytics = self.gps.trail_analytics(points)
        cap_hours = self.gps._TRAIL_MAX_GAP_SECONDS / 3600.0
        self.assertAlmostEqual(analytics["idling_hours"], cap_hours, places=3)

    def test_speed_average_ignores_the_stationary_points(self):
        points = [
            self._point(0, speed=0),
            self._point(1, speed=40),
            self._point(2, speed=60),
        ]
        analytics = self.gps.trail_analytics(points)
        self.assertAlmostEqual(analytics["speed_avg"], 50.0, places=3)
        self.assertAlmostEqual(analytics["speed_max"], 60.0, places=3)

    def test_odometer_distance_uses_first_and_last_not_min_and_max(self):
        points = [
            self._point(0, real_odometer=1000.0),
            self._point(1, real_odometer=9999.0, odometer_valid=False),
            self._point(2, real_odometer=1050.0),
        ]
        analytics = self.gps.trail_analytics(points)
        self.assertAlmostEqual(analytics["odometer_start"], 1000.0, places=2)
        self.assertAlmostEqual(analytics["odometer_end"], 1050.0, places=2)
        self.assertAlmostEqual(analytics["distance_odo"], 50.0, places=2)

    def test_gps_drift_is_not_distance(self):
        points = [
            self._point(0, latitude=19.4000000, longitude=-99.1000000),
            self._point(1, latitude=19.4000500, longitude=-99.1000000),
        ]
        self.assertEqual(self.gps.trail_analytics(points)["distance_gps"], 0.0)

    def test_real_movement_is_distance(self):
        points = [
            self._point(0, latitude=19.4, longitude=-99.1),
            self._point(1, latitude=19.5, longitude=-99.1),
        ]
        distance = self.gps.trail_analytics(points)["distance_gps"]
        self.assertGreater(distance, 10.0)
        self.assertLess(distance, 12.0)

    def test_a_stop_is_a_transition_not_a_state(self):
        points = [
            self._point(0, ignition=True),
            self._point(1, ignition=False),
            self._point(2, ignition=False),
            self._point(3, ignition=False),
            self._point(4, ignition=True),
            self._point(5, ignition=False),
        ]
        self.assertEqual(self.gps.trail_analytics(points)["stop_count"], 2)

    def test_fuel_uses_litres_when_the_bus_reports_them(self):
        points = [
            self._point(0, fuel_level_l=60.0),
            self._point(10, fuel_level_l=45.0),
        ]
        analytics = self.gps.trail_analytics(points)
        self.assertAlmostEqual(analytics["fuel_start"], 60.0, places=2)
        self.assertAlmostEqual(analytics["fuel_end"], 45.0, places=2)
        self.assertAlmostEqual(analytics["fuel_consumed"], 15.0, places=2)

    def test_a_percentage_is_converted_with_the_tank(self):
        points = [
            self._point(0, device_id=7, fuel_level=100.0),
            self._point(10, device_id=7, fuel_level=50.0),
        ]
        analytics = self.gps.trail_analytics(points, {7: 80.0})
        self.assertAlmostEqual(analytics["fuel_start"], 80.0, places=2)
        self.assertAlmostEqual(analytics["fuel_end"], 40.0, places=2)
        self.assertAlmostEqual(analytics["fuel_consumed"], 40.0, places=2)

    def test_a_percentage_without_a_tank_is_not_guessed_at(self):
        points = [
            self._point(0, device_id=7, fuel_level=100.0),
            self._point(10, device_id=7, fuel_level=50.0),
        ]
        self.assertEqual(self.gps.trail_analytics(points, {})["fuel_consumed"], 0.0)

    def test_refuelling_is_not_negative_consumption(self):
        points = [
            self._point(0, fuel_level_l=20.0),
            self._point(10, fuel_level_l=70.0),
        ]
        self.assertEqual(self.gps.trail_analytics(points)["fuel_consumed"], 0.0)


@tagged("post_install", "-at_install")
class TestTrailCoordinates(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gps = cls.env["device.data.log.gps"]

    def _point(self, minutes, latitude, longitude):
        return {
            "timestamp": _START + timedelta(minutes=minutes),
            "latitude": latitude,
            "longitude": longitude,
        }

    def test_coordinates_come_back_as_lon_lat(self):
        coords, _stamps = self.gps.trail_coordinates([self._point(0, 19.4, -99.1)])
        self.assertEqual(coords, [(-99.1, 19.4)])

    def test_a_parked_vehicle_collapses_to_one_point(self):
        coords, stamps = self.gps.trail_coordinates(
            [self._point(index, 19.4, -99.1) for index in range(5)]
        )
        self.assertEqual(len(coords), 1)
        self.assertEqual(len(stamps), 1)

    def test_null_island_is_dropped_but_the_equator_is_not(self):
        coords, _stamps = self.gps.trail_coordinates(
            [
                self._point(0, 0.0, 0.0),
                self._point(1, 0.0, -99.1),
                self._point(2, 19.4, 0.0),
            ]
        )
        self.assertEqual(coords, [(-99.1, 0.0), (0.0, 19.4)])

    def test_timestamps_pair_with_the_coordinates_kept(self):
        coords, stamps = self.gps.trail_coordinates(
            [
                self._point(0, 19.4, -99.1),
                self._point(1, 19.4, -99.1),
                self._point(2, 19.5, -99.2),
            ]
        )
        self.assertEqual(len(coords), len(stamps))
        self.assertEqual(len(coords), 2)


@tagged("post_install", "-at_install")
class TestTrailPoints(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(name="Trail Config")
        cls.device = cls._create_device_device(config=cls.config, identifier="TRAIL-1")
        cls.other = cls._create_device_device(config=cls.config, identifier="TRAIL-2")
        cls.gps = cls.env["device.data.log.gps"]

    def _store(self, device, minutes, latitude=19.4, longitude=-99.1):
        return self.gps.create(
            {
                "device_id": device.id,
                "timestamp": _START + timedelta(minutes=minutes),
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    def test_only_the_columns_a_trail_needs_come_back(self):
        self._store(self.device, 0)
        rows = self.gps.trail_points(
            self.device.ids, _START, _START + timedelta(hours=1)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            set(rows[0]) - {"id"},
            set(self.gps._TRAIL_FIELDS) | {"binding_id", "resource_id"},
            "the fetch is reading columns a trail does not use",
        )

    def test_device_id_is_a_plain_id(self):
        self._store(self.device, 0)
        rows = self.gps.trail_points(
            self.device.ids, _START, _START + timedelta(hours=1)
        )
        self.assertEqual(rows[0]["device_id"], self.device.id)

    def test_rows_are_scoped_to_the_devices_asked_for(self):
        self._store(self.device, 0)
        self._store(self.other, 1)
        rows = self.gps.trail_points(
            self.device.ids, _START, _START + timedelta(hours=1)
        )
        self.assertEqual([row["device_id"] for row in rows], [self.device.id])

    def test_rows_are_scoped_to_the_window(self):
        self._store(self.device, 0)
        self._store(self.device, 600)
        rows = self.gps.trail_points(
            self.device.ids, _START, _START + timedelta(hours=1)
        )
        self.assertEqual(len(rows), 1)

    def test_rows_are_ordered_oldest_first(self):
        for minutes in (30, 0, 15):
            self._store(self.device, minutes)
        rows = self.gps.trail_points(
            self.device.ids, _START, _START + timedelta(hours=1)
        )
        stamps = [row["timestamp"] for row in rows]
        self.assertEqual(stamps, sorted(stamps))

    def test_points_without_a_fix_are_excluded(self):
        self._store(self.device, 0, latitude=0.0, longitude=0.0)
        self._store(self.device, 1)
        rows = self.gps.trail_points(
            self.device.ids, _START, _START + timedelta(hours=1)
        )
        self.assertEqual(len(rows), 1)

    def test_the_limit_is_honoured(self):
        for minutes in range(6):
            self._store(self.device, minutes, latitude=19.4 + minutes * 1e-3)
        rows = self.gps.trail_points(
            self.device.ids, _START, _START + timedelta(hours=1), limit=3
        )
        self.assertEqual(len(rows), 3)

from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestMobileIngest(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(name="Mobile Ingest Config")
        cls.device = cls._create_device_device(
            config=cls.config, name="Phone", identifier="PHONE-INGEST"
        )
        cls.gps = cls.env["device.data.log.gps"]
        cls.base = datetime(2026, 8, 9, 12, 0, 0)

    def _fixes(self, count=5, start=0):
        return [
            {
                "lat": 19.4 + (start + i) * 1e-4,
                "lon": -99.1 + (start + i) * 1e-4,
                "speed": 13.9,
                "timestamp": int(
                    (self.base + timedelta(seconds=30 * (start + i))).timestamp() * 1000
                ),
            }
            for i in range(count)
        ]

    def _stored(self):
        return self.gps.search_count([("device_id", "=", self.device.id)])

    def test_resending_a_batch_stores_nothing_new(self):
        fixes = self._fixes(50)
        first = self.gps.create_from_mobile(self.device, fixes)
        self.assertEqual(len(first), 50)
        self.assertEqual(self._stored(), 50)

        second = self.gps.create_from_mobile(self.device, fixes)
        self.assertFalse(second, "a re-sent batch created records")
        self.assertEqual(self._stored(), 50, "the offline flush was double-counted")

    def test_a_partial_resend_stores_only_what_is_new(self):
        self.gps.create_from_mobile(self.device, self._fixes(10))
        self.assertEqual(self._stored(), 10)

        overlapping = self._fixes(10, start=5)
        created = self.gps.create_from_mobile(self.device, overlapping)
        self.assertEqual(len(created), 5)
        self.assertEqual(self._stored(), 15)

    def test_a_batch_that_repeats_itself_is_deduplicated(self):
        fixes = self._fixes(3)
        created = self.gps.create_from_mobile(self.device, fixes + fixes)
        self.assertEqual(len(created), 3)

    def test_distinct_fixes_at_the_same_instant_are_both_kept(self):
        stamp = int(self.base.timestamp() * 1000)
        created = self.gps.create_from_mobile(
            self.device,
            [
                {"lat": 19.4, "lon": -99.1, "timestamp": stamp},
                {"lat": 19.5, "lon": -99.2, "timestamp": stamp},
            ],
        )
        self.assertEqual(len(created), 2)

    def test_another_device_is_not_deduplicated_against(self):
        other = self._create_device_device(
            config=self.config, name="Phone 2", identifier="PHONE-INGEST-2"
        )
        fixes = self._fixes(4)
        self.gps.create_from_mobile(self.device, fixes)
        created = self.gps.create_from_mobile(other, fixes)
        self.assertEqual(
            len(created), 4, "one phone's fixes suppressed another phone's"
        )

    def _rows_read_by_dedup(self, model, resend):
        read = []
        original = type(model).search_read

        def counting(records, *args, **kwargs):
            rows = original(records, *args, **kwargs)
            read.append(len(rows))
            return rows

        with patch.object(type(model), "search_read", counting):
            ingest = model.ingest_from_mobile(self.device, resend)
        return ingest, sum(read)

    def test_a_resend_reads_the_stored_rows_at_its_stamps_not_the_span(self):
        stored = self._fixes(300)
        self.gps.create_from_mobile(self.device, stored)
        self.env.flush_all()

        ingest, rows = self._rows_read_by_dedup(self.gps, [stored[0], stored[-1]])

        self.assertEqual(ingest.duplicates, 2)
        self.assertLessEqual(rows, 2, f"read {rows} stored fixes to dedup 2")

    def test_speed_is_converted_from_metres_per_second(self):
        created = self.gps.create_from_mobile(
            self.device,
            [{"lat": 19.4, "lon": -99.1, "speed": 13.9, "timestamp": 1754740800000}],
        )
        self.assertAlmostEqual(created.speed, 50.04, places=2)

    def test_a_phone_that_already_sends_kmh_can_say_so(self):
        created = self.gps.create_from_mobile(
            self.device,
            [
                {
                    "lat": 19.4,
                    "lon": -99.1,
                    "speed": 50.0,
                    "speed_unit": "kmh",
                    "timestamp": 1754740800000,
                }
            ],
        )
        self.assertAlmostEqual(created.speed, 50.0, places=2)

    def test_gps_noise_while_stationary_is_not_movement(self):
        created = self.gps.create_from_mobile(
            self.device,
            [{"lat": 19.4, "lon": -99.1, "speed": 0.1, "timestamp": 1754740800000}],
        )
        self.assertFalse(created.movement)

    def test_real_movement_is_flagged(self):
        created = self.gps.create_from_mobile(
            self.device,
            [{"lat": 19.4, "lon": -99.1, "speed": 13.9, "timestamp": 1754740800000}],
        )
        self.assertTrue(created.movement)

    def test_a_batch_is_created_in_one_pass(self):
        fixes = self._fixes(40)
        self.env.flush_all()
        before = self.env.cr.sql_statement_count
        self.gps.create_from_mobile(self.device, fixes)
        self.env.flush_all()
        queries = self.env.cr.sql_statement_count - before
        self.assertLess(
            queries,
            len(fixes),
            f"storing {len(fixes)} fixes took {queries} queries — "
            f"the per-record create loop is back",
        )

    def test_a_junk_alias_does_not_lose_the_fix(self):
        created = self.gps.create_from_mobile(
            self.device,
            [
                {
                    "latitude": 19.4,
                    "lat": "n/a",
                    "longitude": -99.1,
                    "timestamp": 1754740800000,
                }
            ],
        )
        self.assertEqual(len(created), 1)
        self.assertAlmostEqual(created.latitude, 19.4, places=4)

    def test_a_fix_with_no_usable_coordinate_is_still_skipped(self):
        created = self.gps.create_from_mobile(
            self.device,
            [{"latitude": "n/a", "lat": "also junk", "longitude": -99.1}],
        )
        self.assertFalse(created)

    def test_malformed_fixes_are_skipped_not_fatal(self):
        created = self.gps.create_from_mobile(
            self.device,
            [
                {"lat": 19.4, "lon": -99.1, "timestamp": 1754740800000},
                {"lat": "nonsense", "lon": -99.1},
                {"lon": -99.1},
                "not a dict",
                {"lat": 999.0, "lon": -99.1},
            ],
        )
        self.assertEqual(len(created), 1)

    def test_an_out_of_range_timestamp_does_not_poison_the_batch(self):
        created = self.gps.create_from_mobile(
            self.device,
            [
                {"lat": 19.4, "lon": -99.1, "timestamp": 1754740800000},
                {"lat": 19.5, "lon": -99.2, "timestamp": "99999999999999999999"},
            ],
        )
        self.assertEqual(len(created), 2)
        self.assertTrue(all(fix.timestamp for fix in created))

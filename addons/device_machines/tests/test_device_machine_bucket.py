from datetime import UTC, datetime

from psycopg import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import DeviceMachinesCommon


@tagged("post_install", "-at_install")
class TestRemoteMachineBucket(DeviceMachinesCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Bucket = cls.env["device.machine.bucket"]

    def setUp(self):
        super().setUp()
        self._create_counter(self.device, 100, self._ts(13, 55))

    def _ts(self, hour, minute=0, second=0):
        return datetime(2026, 6, 18, hour, minute, second, tzinfo=UTC)

    def test_first_reading_opens_bucket_from_the_baseline(self):
        bucket = self._reading(self.device, self._ts(14, 5), 150)

        self.assertEqual(bucket.device_id, self.device)
        self.assertEqual(bucket.bucket_start, datetime(2026, 6, 18, 14, 0, 0))
        self.assertEqual(bucket.count_start, 100)
        self.assertEqual(bucket.count_end, 150)
        self.assertEqual(bucket.delta, 50)
        self.assertEqual(bucket.msg_count, 1)
        self.assertFalse(bucket.reset_detected)

    def test_second_reading_same_hour_accumulates(self):
        first = self._reading(self.device, self._ts(14, 5), 120)
        second = self._reading(self.device, self._ts(14, 40), 150)

        self.assertEqual(first, second)
        self.assertEqual(second.count_start, 100)
        self.assertEqual(second.count_end, 150)
        self.assertEqual(second.delta, 50)
        self.assertEqual(second.msg_count, 2)
        self.assertEqual(second.bucket_end, datetime(2026, 6, 18, 14, 40, 0))

    def test_new_hour_opens_new_bucket_continuing_the_count(self):
        first = self._reading(self.device, self._ts(14, 5), 192)
        second = self._reading(self.device, self._ts(15, 5), 202)

        self.assertNotEqual(first, second)
        self.assertEqual(
            self.Bucket.search_count([("device_id", "=", self.device.id)]), 2
        )
        self.assertEqual(second.count_start, 192)
        self.assertEqual(second.delta, 10)

    def test_idle_hour_opens_no_bucket(self):
        self._reading(self.device, self._ts(14, 5), 150)

        idle = self._reading(self.device, self._ts(16, 5), 150)

        self.assertFalse(idle)
        self.assertFalse(
            self.Bucket.search_count(
                [
                    ("device_id", "=", self.device.id),
                    ("bucket_start", "=", datetime(2026, 6, 18, 16, 0, 0)),
                ]
            )
        )

    def test_production_after_a_weekly_reset_is_counted(self):
        self._reading(self.device, self._ts(14, 5), 915)

        self._reading(self.device, self._ts(15, 0), 0)
        bucket = self._reading(self.device, self._ts(16, 5), 40)

        self.assertTrue(bucket, "output after a reset must still open a bucket")
        self.assertEqual(bucket.count_start, 0)
        self.assertEqual(bucket.delta, 40)

    def test_first_reading_ever_is_not_counted_as_production(self):
        fresh = self._make_counter_device("Tapadora", "Tapadora")

        first = self._reading(fresh, self._ts(9, 0), 5000)

        self.assertFalse(first, "a standing counter must not become production")

    def test_reset_arriving_on_an_empty_hour_opens_no_bucket(self):
        self.device.last_count = 500

        bucket = self._reading(self.device, self._ts(16, 1), 0)

        self.assertFalse(bucket)

    def test_reset_detected_on_update_keeps_delta(self):
        self._reading(self.device, self._ts(17, 1), 200)
        self._reading(self.device, self._ts(17, 30), 500)

        bucket = self._reading(self.device, self._ts(17, 45), 0)

        self.assertTrue(bucket.reset_detected)
        self.assertEqual(bucket.count_end, 0)
        self.assertEqual(bucket.count_carried, 400)
        self.assertEqual(bucket.delta, 400)

    def test_redelivered_lower_reading_cannot_shrink_the_delta(self):
        bucket = self._reading(self.device, self._ts(14, 40), 180)

        replayed = self._reading(self.device, self._ts(14, 50), 120)

        self.assertEqual(replayed, bucket)
        self.assertEqual(bucket.count_end, 180)
        self.assertEqual(bucket.delta, 80)

    @mute_logger("odoo.db.cursor")
    def test_unique_constraint_device_hour(self):
        self.Bucket.create(
            {
                "device_id": self.device.id,
                "bucket_start": datetime(2026, 6, 18, 14, 0, 0),
            }
        )
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Bucket.create(
                {
                    "device_id": self.device.id,
                    "bucket_start": datetime(2026, 6, 18, 14, 0, 0),
                }
            )
            self.env.flush_all()

    @mute_logger("odoo.db.cursor")
    def test_negative_delta_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Bucket.create(
                {
                    "device_id": self.device.id,
                    "bucket_start": datetime(2026, 6, 18, 20, 0, 0),
                    "delta": -5,
                }
            )
            self.env.flush_all()

    @mute_logger("odoo.db.cursor")
    def test_device_with_history_cannot_be_deleted(self):
        self._reading(self.device, self._ts(14, 5), 150)
        self.assertTrue(
            self.Bucket.search_count([("device_id", "=", self.device.id)]),
            "the fixture must have history for the restriction to apply",
        )

        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.device.unlink()
            self.env.flush_all()

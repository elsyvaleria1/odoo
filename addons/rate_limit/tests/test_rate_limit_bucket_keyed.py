from odoo.tests import TransactionCase, tagged

_KEY = "test.subject:keyed:global"


@tagged("post_install", "-at_install")
class TestConsumeForKey(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Bucket = self.env["rate.limit.bucket"]
        self.addCleanup(self._drop)

    def _drop(self):
        self.env.cr.execute(
            "DELETE FROM rate_limit_bucket WHERE bucket_key LIKE 'test.subject:%'"
        )

    def _bucket(self, key=_KEY):
        return self.Bucket.search([("bucket_key", "=", key)], limit=1)

    def test_no_record_is_needed(self):
        allowed = self.Bucket.consume_for_key(
            _KEY, subject_model="test.subject", subject_id=7, capacity=3
        )

        self.assertTrue(allowed)
        bucket = self._bucket()
        self.assertEqual(bucket.endpoint_model, "test.subject")
        self.assertEqual(bucket.endpoint_id, 7)
        self.assertEqual(bucket.tokens, 2.0)

    def test_it_refuses_at_the_capacity(self):
        verdicts = [
            self.Bucket.consume_for_key(
                _KEY, subject_model="test.subject", subject_id=7, capacity=3
            )
            for _ in range(5)
        ]
        self.assertEqual(verdicts[:3], [True, True, True])
        self.assertIn(False, verdicts, f"the capacity never bit: {verdicts}")

    def test_subjects_do_not_share_a_bucket(self):
        for _ in range(3):
            self.Bucket.consume_for_key(
                _KEY, subject_model="test.subject", subject_id=7, capacity=3
            )
        self.assertFalse(
            self.Bucket.consume_for_key(
                _KEY, subject_model="test.subject", subject_id=7, capacity=3
            )
        )

        self.assertTrue(
            self.Bucket.consume_for_key(
                "test.subject:other:global",
                subject_model="test.subject",
                subject_id=8,
                capacity=3,
            ),
            "a second subject must not inherit the first one's exhaustion",
        )

    def test_refill_rate_defaults_to_one_capacity_per_window(self):
        self.Bucket.consume_for_key(
            _KEY,
            subject_model="test.subject",
            subject_id=7,
            capacity=60,
            window_seconds=60,
        )
        bucket = self._bucket()

        self.assertEqual(bucket.tokens, 59.0)
        self.assertEqual(
            bucket._refilled_tokens(
                0.0,
                bucket.last_refill,
                bucket.last_refill.replace(microsecond=0),
                capacity=60,
                refill_rate=1.0,
            ),
            0.0,
        )

    def test_an_existing_bucket_is_reused_not_duplicated(self):
        for _ in range(2):
            self.Bucket.consume_for_key(
                _KEY, subject_model="test.subject", subject_id=7, capacity=5
            )

        self.env.cr.execute(
            "SELECT count(*) FROM rate_limit_bucket WHERE bucket_key = %s", (_KEY,)
        )
        self.assertEqual(self.env.cr.fetchone()[0], 1)

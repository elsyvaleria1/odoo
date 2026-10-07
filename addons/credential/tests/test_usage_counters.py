from contextlib import contextmanager, nullcontext
from unittest.mock import patch

import psycopg

from odoo import fields
from odoo.tests import TransactionCase

from odoo.addons.credential.models.credential_credential import _flush_usage
from odoo.addons.credential.tests.common import flush_after_commit


class TestUsageCounters(TransactionCase):
    def setUp(self):
        super().setUp()
        self.credential = self.env["credential.credential"].create(
            {
                "name": "counted",
                "category_id": self.env.ref(
                    "credential.credential_category_api_key"
                ).id,
                "api_key": "K",
            }
        )

    def _stored(self):
        """The counters as the row holds them in this transaction."""
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT usage_count, success_count, error_count, success_rate, "
            "last_used_at FROM credential_credential WHERE id = %s",
            [self.credential.id],
        )
        return self.env.cr.fetchone()

    def test_a_use_writes_nothing_in_the_callers_transaction(self):
        before = self._stored()

        self.credential.increment_usage(success=True)
        self.credential.increment_usage(success=False)
        self.credential.mark_as_used()

        self.assertEqual(
            self._stored(),
            before,
            "the caller's transaction must not lock the credential's row",
        )

    def test_uses_are_added_after_the_commit(self):
        for success in (True, True, True, False):
            self.credential.increment_usage(success=success)
        self.credential.mark_as_used()

        flush_after_commit(self.env)

        credential = self.credential
        self.assertEqual(
            (credential.usage_count, credential.success_count, credential.error_count),
            (4, 3, 1),
        )
        self.assertEqual(credential.success_rate, 75.0)
        self.assertTrue(credential.last_used_at)
        credential._compute_success_rate()
        self.assertEqual(
            credential.success_rate, 75.0, "the stored rate is the computed one"
        )

    def test_a_later_transaction_adds_to_what_an_earlier_one_counted(self):
        self.credential.increment_usage(success=True)
        flush_after_commit(self.env)
        self.credential.increment_usage(success=False)
        flush_after_commit(self.env)

        self.assertEqual(
            (
                self.credential.usage_count,
                self.credential.success_count,
                self.credential.error_count,
                self.credential.success_rate,
            ),
            (2, 1, 1, 50.0),
        )

    def test_a_rolled_back_transaction_still_counts_its_uses(self):
        self.credential.increment_usage(success=False)
        self.env.flush_all()
        self.env.cr.postcommit.clear()

        with patch.object(
            self.env.registry, "cursor", lambda: nullcontext(self.env.cr)
        ):
            self.env.cr.postrollback.run()
        self.env.invalidate_all()

        self.assertEqual(
            (self.credential.usage_count, self.credential.error_count), (1, 1)
        )

    def _losing_registry(self, losses):
        """A registry whose cursors lose `losses` times to a concurrent update,
        then are this test's own."""
        tries = []
        cr = self.env.cr

        class Losing:
            def execute(self, *args, **kwargs):
                raise psycopg.errors.SerializationFailure("concurrent update")

        @contextmanager
        def cursor():
            tries.append(len(tries) + 1)
            yield Losing() if len(tries) <= losses else cr

        return type("Registry", (), {"cursor": staticmethod(cursor)}), tries

    def test_a_flush_lost_to_a_concurrent_one_is_run_again(self):
        registry, tries = self._losing_registry(losses=1)
        pending = {self.credential.id: [1, 1, 0, fields.Datetime.now()]}

        _flush_usage(registry, pending)
        self.env.invalidate_all()

        self.assertEqual(tries, [1, 2])
        self.assertEqual(self.credential.usage_count, 1)
        self.assertFalse(pending, "what was flushed is not flushed twice")

    def test_a_flush_that_keeps_losing_gives_up_and_lets_the_caller_be(self):
        registry, tries = self._losing_registry(losses=99)
        pending = {self.credential.id: [1, 1, 0, fields.Datetime.now()]}

        with self.assertLogs(
            "odoo.addons.credential.models.credential_credential", "WARNING"
        ):
            _flush_usage(registry, pending)
        self.env.invalidate_all()

        self.assertEqual(tries, [1, 2, 3])
        self.assertEqual(self.credential.usage_count, 0)

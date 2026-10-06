import threading
import time
import uuid
import zlib

from odoo.tests import TransactionCase, tagged

from odoo.addons.integration.models.integration_exchange import FINGERPRINTS_MAX
from odoo.addons.integration.models.mixin_inbound_gate import DEFAULT_MAX_PAYLOAD_SIZE


@tagged("post_install", "-at_install", "integration")
class TestRecordReceiver(TransactionCase):
    def _for_record(self, name, purpose=None):
        with self.sync_env_with_side_cursors():
            return self.env["integration.receiver"]._for_record(
                self.env.company, name, purpose=purpose
            )

    def test_one_record_keeps_one_receiver_per_purpose(self):
        first = self._for_record("First flow", purpose="first_flow")
        second = self._for_record("Second flow", purpose="second_flow")

        self.assertNotEqual(first, second)
        self.assertEqual(self._for_record("Renamed", purpose="first_flow"), first)
        self.assertEqual(
            (first.res_model, first.res_id, first.res_purpose),
            ("res.company", self.env.company.id, "first_flow"),
        )
        self.assertNotEqual(first.code, second.code)
        self.assertEqual(first.auth_type, "caller_check")

    def test_an_archived_receiver_refuses_every_call(self):
        receiver = self._for_record("Archived flow", purpose="archived_flow")
        receiver.active = False

        self.assertEqual(
            self._for_record("Archived flow", purpose="archived_flow"), receiver
        )
        allowed, status, _reason, code = receiver._decide_inbound_request({})
        self.assertEqual((allowed, status, code), (False, 404, "endpoint_inactive"))

    def test_repeated_failed_authentication_from_one_caller_is_one_row(self):
        receiver = self._for_record("Signed flow", purpose="signed_flow")
        for _ in range(3):
            receiver._store_inbound_refusal(
                "authentication_failed",
                401,
                "bad signature",
                headers={},
                remote_addr="203.0.113.9",
                mode="enforce",
            )
        receiver._store_inbound_refusal(
            "authentication_failed",
            401,
            "bad signature",
            headers={},
            remote_addr="203.0.113.10",
            mode="enforce",
        )
        self.env.flush_all()
        rows = self.env["integration.exchange"].search(
            [
                ("state", "=", "refused"),
                ("refusal_reason", "=", "authentication_failed"),
                ("channel_id", "=", f"{receiver._name},{receiver.id}"),
            ]
        )
        self.assertEqual(
            sorted(rows.mapped("attempt_count")), [1, 3], "one row per caller, counted"
        )
        self.assertEqual(
            rows.mapped("distinct_presented_count"),
            [0, 0],
            "a signature failure presents no credential to fingerprint",
        )

    def _refuse_token(self, receiver, token, address="203.0.113.11"):
        receiver._store_inbound_refusal(
            "authentication_failed",
            401,
            "bad token",
            headers={"Authorization": f"Bearer {token}"},
            remote_addr=address,
            mode="enforce",
        )

    def _refusal_row(self, receiver):
        self.env.flush_all()
        return self.env["integration.exchange"].search(
            [
                ("state", "=", "refused"),
                ("channel_id", "=", f"{receiver._name},{receiver.id}"),
            ]
        )

    def test_a_collapsed_refusal_counts_the_different_credentials_tried(self):
        receiver = self._for_record("Token flow", purpose="token_flow")
        for token in ("alpha", "beta", "alpha", "gamma"):
            self._refuse_token(receiver, token)

        row = self._refusal_row(receiver)
        self.assertEqual(row.attempt_count, 4)
        self.assertEqual(row.distinct_presented_count, 3)
        stored = row.sudo().presented_fingerprints
        self.assertEqual(len(stored), 3)
        for token in ("alpha", "beta", "gamma"):
            self.assertNotIn(token, " ".join(stored), "a credential is never kept")

    def test_the_credentials_counted_on_one_row_are_bounded(self):
        receiver = self._for_record("Guessed flow", purpose="guessed_flow")
        for index in range(FINGERPRINTS_MAX + 5):
            self._refuse_token(receiver, f"guess-{index}")

        row = self._refusal_row(receiver)
        self.assertEqual(row.attempt_count, FINGERPRINTS_MAX + 5)
        self.assertEqual(row.distinct_presented_count, FINGERPRINTS_MAX)
        self.assertEqual(len(row.sudo().presented_fingerprints), FINGERPRINTS_MAX)
        self.assertIn(f"{FINGERPRINTS_MAX}+ credentials", row.display_name)

    def test_one_credential_on_two_gates_has_two_fingerprints(self):
        first = self._for_record("First flow", purpose="first_flow")
        second = self._for_record("Second flow", purpose="second_flow")
        self._refuse_token(first, "same")
        self._refuse_token(second, "same")

        self.assertNotEqual(
            self._refusal_row(first).sudo().presented_fingerprints,
            self._refusal_row(second).sudo().presented_fingerprints,
        )

    def test_a_receiver_without_purpose_is_not_a_purposed_one(self):
        plain = self._for_record("Plain")

        self.assertNotEqual(plain, self._for_record("Purposed", purpose="x"))
        self.assertFalse(plain.res_purpose)

    def test_the_first_call_is_answered_by_the_receiver_it_commits(self):
        purpose = f"first_call_{uuid.uuid4().hex}"
        receivers = self.env["integration.receiver"]
        receivers.search_count([])
        try:
            with self.leave_registry_test_mode():
                receiver = receivers._for_record(
                    self.env.company, "First call", purpose=purpose
                )
                self.assertEqual(receiver.res_purpose, purpose)
                self.assertEqual(
                    receiver._inbound_max_payload_size(), DEFAULT_MAX_PAYLOAD_SIZE
                )
                self.assertEqual(receiver.display_name, "First call")
                self.assertEqual(receiver.auth_type, "caller_check")
        finally:
            with self.leave_registry_test_mode(), self.registry.cursor() as cr:
                cr.execute(
                    "DELETE FROM integration_receiver WHERE res_purpose = %s",
                    [purpose],
                )

    def test_a_caller_queued_on_the_lock_takes_the_receiver_committed_before_it(
        self,
    ):
        purpose = f"queued_{uuid.uuid4().hex}"
        company = self.env.company
        queued = {}
        try:
            with self.leave_registry_test_mode():
                with self.registry.cursor() as holder:
                    holder.execute(
                        "SELECT pg_advisory_xact_lock(%s, %s)",
                        [zlib.crc32(company._name.encode()) & 0x7FFFFFFF, company.id],
                    )
                    first = (
                        self.env(cr=holder)["integration.receiver"]
                        .sudo()
                        .create(
                            {
                                "name": "Holder",
                                "code": f"holder_{purpose}",
                                "res_model": company._name,
                                "res_id": company.id,
                                "res_purpose": purpose,
                                "auth_type": "caller_check",
                            }
                        )
                    )

                    def call():
                        with self.registry.cursor() as cr:
                            env = self.env(cr=cr)
                            queued["id"] = (
                                env["integration.receiver"]
                                ._for_record(env.company, "Queued", purpose=purpose)
                                .id
                            )

                    caller = threading.Thread(target=call)
                    caller.start()
                    time.sleep(0.5)
                    self.assertTrue(caller.is_alive(), "the caller waits on the lock")
                    holder.commit()
                caller.join(10)
                with self.registry.cursor() as cr:
                    cr.execute(
                        "SELECT id FROM integration_receiver WHERE res_purpose = %s",
                        [purpose],
                    )
                    committed = [row[0] for row in cr.fetchall()]
            self.assertEqual(
                committed,
                [first.id],
                "the queued caller read under the lock a snapshot older than the "
                "holder's commit, and created a second receiver",
            )
            self.assertEqual(queued, {"id": first.id})
        finally:
            with self.leave_registry_test_mode(), self.registry.cursor() as cr:
                cr.execute(
                    "DELETE FROM integration_receiver WHERE res_purpose = %s",
                    [purpose],
                )

import threading
import time
import uuid
import zlib

from odoo.tests import TransactionCase, tagged

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

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "integration")
class TestReceiverDeletion(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.receiver = cls.env["integration.receiver"].create(
            {"name": "Probe receiver", "code": "probe_deletion", "auth_type": "none"}
        )
        cls.ref = f"integration.receiver,{cls.receiver.id}"

    def _exchange(self, state, age_days=0):
        return (
            self.env["integration.exchange"]
            .sudo()
            .create(
                {
                    "direction": "inbound",
                    "channel_id": self.ref,
                    "state": state,
                    "date_completed": fields.Datetime.now() - timedelta(days=age_days),
                }
            )
        )

    def test_a_receiver_with_refusals_can_be_deleted_and_they_stay(self):
        admitted = self._exchange("success")
        failed = self._exchange("failed")
        refused = self._exchange("refused")

        self.receiver.unlink()

        self.assertFalse(self.receiver.exists())
        self.assertFalse(admitted.exists())
        self.assertFalse(failed.exists())
        self.assertTrue(refused.exists())

    def test_the_retention_sweep_removes_a_refusal_its_endpoint_left(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "integration.log_retention_days", "30"
        )
        old = self._exchange("refused", age_days=60)
        recent = self._exchange("refused", age_days=10)
        self.receiver.unlink()

        self.env["integration.exchange"]._gc_old_logs()

        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

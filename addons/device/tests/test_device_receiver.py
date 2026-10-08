import importlib.util
from pathlib import Path

from odoo.exceptions import AccessDenied
from odoo.tests import TransactionCase, tagged

from odoo.addons.base.models.ir_cron import is_user_archived

MIGRATION = Path(__file__).parents[1] / "migrations" / "2.3.2" / "post-migrate.py"


def _migration():
    spec = importlib.util.spec_from_file_location(
        "device_receiver_migration", MIGRATION
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("post_install", "-at_install")
class TestDeviceReceiver(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.receiver = cls.env.ref("device.user_device_receiver")

    def test_the_receiver_runs_the_jobs_its_pushes_queue(self):
        self.assertTrue(self.receiver.active)
        self.assertEqual(self.receiver.principal_type, "service")
        self.assertFalse(is_user_archived(self.env(user=self.receiver)))

    def test_the_receiver_still_never_logs_in(self):
        with self.assertRaises(AccessDenied):
            self.env["res.users"].authenticate(
                {"type": "password", "login": "__device_receiver__", "password": "x"},
                {"interactive": True},
            )

    def _failed_reading(self, attachment):
        return self.env["ir.job"].create(
            {
                "name": f"Read text of {attachment.name}",
                "channel": "root",
                "model_name": "ir.attachment",
                "method_name": "_job_read",
                "record_ids": attachment.ids,
                "args": ["text"],
                "kwargs": {},
                "user_id": self.receiver.id,
                "state": "failed",
                "exc_name": "TerminalJobError",
            }
        )

    def test_the_upgrade_wakes_the_receiver_and_reads_again_what_it_failed(self):
        pending, done = (
            self.env["ir.attachment"]
            .with_user(self.receiver)
            .create(
                [
                    {"name": "pending.txt", "raw": b"pending"},
                    {"name": "done.txt", "raw": b"done"},
                ]
            )
        )
        self._failed_reading(pending)
        self._failed_reading(done)
        self.env["ir.attachment"].browse(done.id)._store_reading(
            "text", "done", announce=False
        )
        self.receiver.active = False

        _migration().migrate(self.env.cr, "19.0.2.3.1")

        self.assertTrue(self.receiver.active)
        requeued = self.env["ir.job"].search(
            [("state", "!=", "failed"), ("method_name", "=", "_job_read")]
        )
        self.assertEqual([tuple(job.record_ids) for job in requeued], [(pending.id,)])
        self.assertEqual(requeued.user_id, self.receiver)
        self.assertTrue(requeued.elevated, "as elevated as the push that queued it")

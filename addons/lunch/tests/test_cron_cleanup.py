from odoo.addons.lunch.tests.common import TestsCommon
from odoo.addons.lunch.tools.cron_cleanup import unlink_records_with_cron_cleanup


class TestLunchCronCleanup(TestsCommon):
    def test_alert_batch_removes_crons_and_server_actions(self):
        records = self.alert_ny | self.alert_tokyo
        crons = records.cron_id.sudo()
        actions = crons.ir_actions_server_id
        records.unlink()
        self.assertFalse(records.exists())
        self.assertFalse(crons.exists())
        self.assertFalse(actions.exists())

    def test_supplier_batch_removes_crons_and_server_actions(self):
        partners = self.env["res.partner"].create(
            [{"name": "Cleanup A"}, {"name": "Cleanup B"}]
        )
        records = self.env["lunch.supplier"].create(
            [{"partner_id": partner.id, "send_by": "phone"} for partner in partners]
        )
        crons = records.cron_id.sudo()
        actions = crons.ir_actions_server_id
        records.unlink()
        self.assertFalse(records.exists())
        self.assertFalse(crons.exists())
        self.assertFalse(actions.exists())

    def test_failed_parent_unlink_keeps_crons_and_server_actions(self):
        crons = self.alert_ny.cron_id.sudo()
        actions = crons.ir_actions_server_id

        def reject():
            raise ValueError("Parent refused")

        with self.assertRaisesRegex(ValueError, "Parent refused"):
            unlink_records_with_cron_cleanup(crons, reject)
        self.assertEqual(crons.exists(), crons)
        self.assertEqual(actions.exists(), actions)

    def test_empty_cleanup_preserves_callback_result(self):
        marker = object()
        self.assertIs(
            unlink_records_with_cron_cleanup(self.env["ir.cron"], lambda: marker),
            marker,
        )

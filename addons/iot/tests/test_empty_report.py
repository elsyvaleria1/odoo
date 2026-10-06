from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEmptyReport(TransactionCase):
    def test_a_template_mailing_explains_a_report_only_an_iot_box_prints(self):
        self.env["ir.ui.view"].create(
            {
                "type": "qweb",
                "name": "iot.test_empty_report",
                "key": "iot.test_empty_report",
                "arch": "<t/>",
            }
        )
        report = self.env["ir.actions.report"].create(
            {
                "name": "Empty label",
                "report_name": "iot.test_empty_report",
                "model": "res.partner",
            }
        )
        partners = self.env["res.partner"].create([{"name": "A"}, {"name": "B"}])
        template = self.env["mail.template"].create(
            {
                "name": "Labels",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "report_template_ids": [Command.set(report.ids)],
            }
        )

        with self.assertRaisesRegex(UserError, "requires an IoT Box"):
            template.with_context(force_report_rendering=True)._prepare_attachment_vals(
                partners.ids, {"report_template_ids"}
            )


@tagged("post_install", "-at_install")
class TestPrintWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        box = cls.env["iot.box"].create(
            {"name": "Printer test", "identifier": "printer-test-box"}
        )
        cls.printers = cls.env["iot.device"].create(
            [
                {"name": name, "identifier": name, "iot_id": box.id, "type": "printer"}
                for name in ("printer-test-a", "printer-test-b")
            ]
        )
        cls.report = cls.env["ir.actions.report"].create(
            {
                "name": "Printer selection",
                "report_name": "iot.printer_test",
                "model": "res.partner",
                "device_ids": [Command.set(cls.printers[:1].ids)],
            }
        )

    def test_printer_action_creates_and_filters_selection(self):
        action = self.report.action_select_printers(self.printers.ids + [999999999])
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertTrue(wizard.exists())
        self.assertEqual(wizard.device_ids, self.printers[:1])
        self.assertEqual(wizard.display_device_ids, self.printers[:1])
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["context"], {"report_id": self.report.id})

    def test_each_action_creates_its_own_empty_selection(self):
        first = self.report.action_select_printers()
        second = self.report.action_select_printers([])
        self.assertNotEqual(first["res_id"], second["res_id"])
        for action in (first, second):
            wizard = self.env[action["res_model"]].browse(action["res_id"])
            self.assertFalse(wizard.device_ids)
            self.assertEqual(wizard.display_device_ids, self.printers[:1])

    def test_empty_report_recordset_is_rejected(self):
        with self.assertRaises(ValueError):
            self.env["ir.actions.report"].action_select_printers()

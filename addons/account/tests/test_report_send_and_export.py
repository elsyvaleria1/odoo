import base64
from unittest.mock import patch

from lxml import etree

from odoo import Command
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestReportSendAndExport(TestAccountReportsCommon):
    def test_send_statements_mails_each_partner_its_own_statement(self):
        partner_with_email = self.env["res.partner"].create(
            {"name": "With Email", "email": "with@example.com"}
        )
        partner_without_email = self.env["res.partner"].create(
            {
                "name": "Without Email",
                "child_ids": [
                    Command.create(
                        {
                            "name": "Billing",
                            "type": "invoice",
                            "email": "billing@example.com",
                        }
                    )
                ],
            }
        )
        partners = partner_with_email + partner_without_email
        report = self.env.ref("account.customer_statement_report")
        options = report.get_options({"partner_ids": partners.ids})
        wizard = (
            self.env["wizard.report.formula.send"]
            .with_context(
                default_report_options=options,
                default_mail_template_id=self.env.ref(
                    "account.email_template_customer_statement"
                ).id,
            )
            .create({"checkbox_download": True})
        )
        self.assertEqual(wizard.mode, "multi")
        self.assertFalse(wizard.warnings)

        def fake_statement_attachment(partner, report, options=None):
            return self.env["ir.attachment"].create(
                {
                    "name": f"statement-{partner.id}.pdf",
                    "raw": b"%PDF fake",
                    "res_model": "res.partner",
                    "res_id": partner.id,
                }
            )

        with patch.object(
            type(self.env["res.partner"]),
            "_create_partner_account_report_attachment",
            fake_statement_attachment,
        ):
            wizard.action_send_and_print()

        for partner, recipients in (
            (partner_with_email, partner_with_email),
            (partner_without_email, partner_without_email.child_ids),
        ):
            message = self.env["mail.message"].search(
                [
                    ("model", "=", "res.partner"),
                    ("res_id", "=", partner.id),
                    ("attachment_ids", "!=", False),
                ],
                order="id desc",
                limit=1,
            )
            self.assertEqual(message.partner_ids, recipients)
            self.assertEqual(
                message.attachment_ids.mapped("name"), [f"statement-{partner.id}.pdf"]
            )

    def test_send_wizard_form_offers_email_and_download(self):
        arch = etree.fromstring(
            self.env["wizard.report.formula.send"].get_views([(False, "form")])[
                "views"
            ]["form"]["arch"]
        )
        for field_name in ("checkbox_send_mail", "checkbox_download"):
            [field_node] = arch.xpath(f"//field[@name='{field_name}']")
            self.assertFalse(field_node.get("invisible"), field_name)

    def test_export_to_attachment_from_url_action(self):
        report = self.env.ref("account.generic_tax_report")
        source = self.env["ir.attachment"].create(
            {"name": "declaration.xml", "raw": b"<declaration/>"}
        )
        export_wizard = self.env["wizard.report.formula.export.attachment"].create(
            {"report_id": report.id}
        )
        export_format = self.env[
            "wizard.report.formula.export.attachment.format"
        ].create(
            {
                "name": "XML",
                "fun_to_call": "export_file",
                "export_wizard_id": export_wizard.id,
            }
        )
        generation_options = {"report_id": report.id, "unfold_all": False}

        vals = export_format.with_context(
            account_report_generation_options=generation_options
        ).apply_export(
            {
                "type": "ir.actions.act_url",
                "url": f"web/content/?model=ir.attachment&id={source.id}"
                "&filename_field=name&field=datas&download=true",
            }
        )

        self.assertEqual(vals["name"], "declaration.xml")
        self.assertEqual(base64.b64decode(vals["datas"]), b"<declaration/>")
        self.assertEqual(json_loads(vals["description"]), generation_options)

    def test_file_generation_without_errors(self):
        report = self.env.ref("account.general_ledger_report")
        options = self._generate_options(report, "2019-01-01", "2019-12-31")

        file_data = report._generate_file_data_with_error_check(
            options, lambda **kwargs: "content", {"file_type": "txt"}
        )

        self.assertEqual(file_data["file_content"], b"content")

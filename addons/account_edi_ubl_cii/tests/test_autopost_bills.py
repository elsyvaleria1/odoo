import base64
from datetime import date, datetime, timedelta

from lxml import etree

from odoo import fields
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAutoPostBills(AccountTestInvoicingCommon):
    def import_facturx(self, filename="facturx_out_invoice.xml", ref=None, date=None):
        self.env.cr._now = datetime.now()
        with file_open(
            f"account_edi_ubl_cii/tests/test_files/{filename}",
            "rb",
            filter_ext=(".xml",),
        ) as file:
            file_read = file.read()
            tree = etree.fromstring(file_read)
            if ref:
                tree.find("./{*}ExchangedDocument/{*}ID").text = ref
            if date:
                tree.find(
                    "./{*}ExchangedDocument/{*}IssueDateTime/{*}DateTimeString"
                ).text = date
            attachment = self.env["ir.attachment"].create(
                {
                    "name": "test_file.xml",
                    "datas": base64.encodebytes(etree.tostring(tree)),
                }
            )
            return (
                self.company_data["default_journal_purchase"]
                .with_context(disable_abnormal_invoice_detection=False)
                ._create_document_from_attachment(attachment.id)
            )

    def assert_wizard(self, post_result, expected_nb_bills):
        self.assertEqual(
            post_result.get("res_model"), "wizard.res.partner.update.bill.autopost"
        )
        wizard = self.env[post_result.get("res_model")].browse(
            post_result.get("res_id")
        )
        self.assertEqual(wizard.nb_unmodified_bills, expected_nb_bills)
        return wizard

    def test_autopost_bills(self):
        move = self.import_facturx()
        autopost_bills_wizard = move.action_post()
        self.assertFalse(autopost_bills_wizard)
        self.assertFalse(move.is_manually_modified)

        move = self.import_facturx()
        autopost_bills_wizard = move.action_post()
        self.assertFalse(autopost_bills_wizard)
        self.assertFalse(move.is_manually_modified)

        move = self.import_facturx()
        autopost_bills_wizard = move.action_post()
        self.assertFalse(move.is_manually_modified)
        wizard = self.assert_wizard(autopost_bills_wizard, 3)
        wizard.action_ask_later()

        move = self.import_facturx()
        autopost_bills_wizard = move.action_post()
        self.assertFalse(move.is_manually_modified)
        wizard = self.assert_wizard(autopost_bills_wizard, 4)
        wizard.action_ask_later()

        move = self.import_facturx().with_context(skip_is_manually_modified=False)
        move.invoice_date_due = fields.Date.today()
        autopost_bills_wizard = move.action_post()
        self.assertFalse(autopost_bills_wizard)
        self.assertTrue(move.is_manually_modified)

        for _ in range(3):
            move = self.import_facturx()
            autopost_bills_wizard = move.action_post()
        wizard = self.assert_wizard(autopost_bills_wizard, 3)
        wizard.action_automate_partner()

        move = self.import_facturx(ref="refbill4", date="20170102")
        self.assertEqual(move.state, "posted")

        move.partner_id.autopost_bills = "ask"

        move = self.import_facturx()
        autopost_bills_wizard = move.action_post()
        wizard = self.assert_wizard(autopost_bills_wizard, 5)
        wizard.action_never_automate_partner()

        move = self.import_facturx()
        self.assertEqual(move.state, "draft")
        autopost_bills_wizard = move.action_post()
        self.assertFalse(autopost_bills_wizard)

        move.partner_id.autopost_bills = "ask"

        move = self.import_facturx()
        autopost_bills_wizard = move.action_post()
        wizard = self.assert_wizard(autopost_bills_wizard, 7)
        wizard.action_ask_later()

        move.company_id.account_config_id.autopost_bills = False
        move.partner_id.autopost_bills = "always"
        move = self.import_facturx()
        self.assertEqual(move.state, "draft")
        autopost_bills_wizard = move.action_post()
        self.assertFalse(autopost_bills_wizard)

        move.company_id.account_config_id.autopost_bills = True
        move.partner_id.autopost_bills = "always"

        move = self.import_facturx(ref="refbill4")
        self.assertEqual(move.state, "draft")

        base_date = date(2018, 1, 1)
        for i in range(10):
            move = self.import_facturx(
                ref=f"ref{i}", date=(base_date + timedelta(days=i)).strftime("%Y%m%d")
            )
            self.assertEqual(move.state, "posted")

        move = self.import_facturx(filename="facturx_out_invoice_abnormal.xml")
        self.assertEqual(move.state, "draft")
        res = move.action_post()
        self.assertEqual(res.get("res_model"), "wizard.account.move.post")
        wizard = self.env[res.get("res_model")].browse(res.get("res_id"))
        self.assertEqual(wizard.move_ids, move)

        self.company_data["default_journal_purchase"].restrict_mode_hash_table = True
        move = self.import_facturx()
        self.assertEqual(move.state, "draft")
        res = move.action_post()
        self.assertFalse(res)

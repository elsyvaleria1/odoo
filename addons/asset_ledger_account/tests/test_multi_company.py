from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAssetLogMultiCompany(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("asset_ledger.group_asset_manager")
        cls.company_a = cls.company_data["company"]
        cls.other_data = cls.setup_other_company()
        cls.company_b = cls.other_data["company"]
        cls.company_b.currency_id = cls.env.ref("base.EUR")
        # The session stays on company A while every bill below belongs to B.
        cls.env.user.sudo().company_ids = [Command.link(cls.company_b.id)]
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                allowed_company_ids=[cls.company_a.id, cls.company_b.id],
            )
        )
        cls.asset_product = (
            cls.env["product.product"]
            .sudo()
            .create(
                {
                    "name": "Cross-company asset",
                    "type": "consu",
                    "is_storable": True,
                    "tracking": "serial",
                    "asset_kind_id": cls.env.ref("resource.kind_vehicle").id,
                }
            )
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Cross-company vendor"})

    def _company_b_bill(self, asset):
        return self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor.id,
                "invoice_date": "2026-01-15",
                "company_id": self.company_b.id,
                "journal_id": self.other_data["default_journal_purchase"].id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "cross-company expense",
                            "account_id": self.other_data["default_account_expense"].id,
                            "asset_id": asset.asset_id.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )

    def test_log_follows_the_bill_company_for_a_company_owned_asset(self):
        asset = self.env["product.trace"].create(
            {
                "name": "XCO-OWNED",
                "product_id": self.asset_product.id,
                "company_id": self.company_b.id,
            }
        )
        self.assertEqual(self.env.company, self.company_a)

        move = self._company_b_bill(asset)
        move.flush_recordset()

        log = move.invoice_line_ids.asset_log_ids
        self.assertEqual(
            log.company_id,
            self.company_b,
            "The log belongs to the bill's company, not to the session's",
        )

    def test_log_follows_the_bill_company_for_a_company_less_asset(self):
        asset = self.env["product.trace"].create(
            {"name": "XCO-SHARED", "product_id": self.asset_product.id}
        )
        self.assertFalse(
            asset.company_id,
            "A lot of a company-less product is itself company-less",
        )
        self.assertEqual(self.env.company, self.company_a)
        self.assertNotEqual(self.company_a.currency_id, self.company_b.currency_id)

        move = self._company_b_bill(asset)
        move.flush_recordset()

        line = move.invoice_line_ids
        log = line.asset_log_ids
        self.assertEqual(log.company_id, self.company_b)
        self.assertEqual(
            log.currency_id,
            move.company_currency_id,
            "The amount is in the bill's company currency, so it must be "
            "labelled with it",
        )
        self.assertEqual(log.amount, line.balance)

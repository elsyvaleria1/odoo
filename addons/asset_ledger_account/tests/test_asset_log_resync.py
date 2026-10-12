from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAssetLogResync(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("asset_ledger.group_asset_manager")
        cls.company = cls.company_data["company"]
        cls.expense_account = cls.company_data["default_account_expense"]

        product = cls.env["product.product"].sudo()
        cls.asset_product = product.create(
            {
                "name": "Resync asset",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("base.kind_machinery").id,
            }
        )
        cls.untyped_category = (
            cls.env["product.category"]
            .sudo()
            .create({"name": "Resync untyped category"})
        )
        cls.service = product.create(
            {
                "name": "Resync service",
                "type": "service",
                "categ_id": cls.untyped_category.id,
            }
        )
        cls.other_service = product.create(
            {
                "name": "Resync other service",
                "type": "service",
                "categ_id": cls.untyped_category.id,
            }
        )
        cls.asset = cls.env["product.trace"].create(
            {
                "name": "RESYNC-1",
                "product_id": cls.asset_product.id,
                "company_id": cls.company.id,
            }
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Resync vendor"})
        cls.other_vendor = cls.env["res.partner"].create({"name": "Resync vendor 2"})

    def _bill(self, product=None, account=None):
        move = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor.id,
                "invoice_date": "2026-01-15",
                "company_id": self.company.id,
                "journal_id": self.company_data["default_journal_purchase"].id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "resync",
                            "product_id": product.id if product else False,
                            "account_id": (account or self.expense_account).id,
                            "asset_id": self.asset.asset_id.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        line = move.invoice_line_ids
        return move, line, line.asset_log_ids

    def test_date_follows_a_corrected_invoice_date(self):
        move, _, log = self._bill()
        self.assertEqual(str(log.date), "2026-01-15")

        move.write({"invoice_date": "2025-11-30"})

        self.assertEqual(
            str(log.date),
            "2025-11-30",
            "date orders the ledger and drives the odometer and efficiency "
            "computes, so a stale one is not cosmetic",
        )

    def test_vendor_follows_a_corrected_partner(self):
        move, _, log = self._bill()
        self.assertEqual(log.vendor_id, self.vendor)

        move.write({"partner_id": self.other_vendor.id})

        self.assertEqual(log.vendor_id, self.other_vendor)

    def test_product_follows_a_corrected_line_product(self):
        _, line, log = self._bill(product=self.service)
        self.assertEqual(log.product_id, self.service)

        line.write({"product_id": self.other_service.id})

        self.assertEqual(log.product_id, self.other_service)

    def test_log_type_follows_a_retargeted_account(self):
        untyped_account = self.expense_account.copy({"code": "RESYNCU"})
        untyped_account.asset_log_type = False
        typed_account = self.expense_account.copy({"code": "RESYNCT"})
        typed_account.asset_log_type = "fuel"

        _, line, log = self._bill(account=untyped_account)
        self.assertFalse(log.log_type)

        line.write({"account_id": typed_account.id})

        self.assertEqual(
            log.log_type,
            "fuel",
            "the typing has to hold itself up",
        )

    def test_a_manual_log_is_not_touched_by_the_resync(self):
        log = self.env["resource.log"].create(
            {
                "asset_id": self.asset.asset_id.id,
                "vendor_id": self.vendor.id,
                "product_id": self.service.id,
                "date": "2026-02-01",
            }
        )

        self.assertEqual(str(log.date), "2026-02-01")
        self.assertEqual(log.vendor_id, self.vendor)
        self.assertEqual(log.product_id, self.service)

        log.write({"notes": "untouched"})

        self.assertEqual(str(log.date), "2026-02-01")
        self.assertEqual(log.vendor_id, self.vendor)
        self.assertEqual(log.product_id, self.service)

    def test_a_manual_log_still_gets_the_default_date(self):
        log = self.env["resource.log"].create({"asset_id": self.asset.asset_id.id})

        self.assertTrue(
            log.date,
            "date carries default=context_today; making it computable must not "
            "leave a manual log dateless",
        )

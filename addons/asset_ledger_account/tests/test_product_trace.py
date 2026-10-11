from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestProductTrace(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref(
            "asset_ledger.group_asset_manager"
        ) | cls.env.ref("account.group_account_readonly")

        cls.test_company = cls.company_data["company"]
        cls.expense_account = cls.company_data["default_account_expense"]
        cls.purchase_journal = cls.company_data["default_journal_purchase"] or (
            cls.env["account.journal"].create(
                {
                    "name": "Test Purchase",
                    "type": "purchase",
                    "code": "TBILL",
                    "company_id": cls.test_company.id,
                }
            )
        )

        cls.AccountMove = cls.env["account.move"].with_company(cls.test_company)
        cls.AccountMoveLine = cls.env["account.move.line"]
        cls.ProductTrace = cls.env["product.trace"]
        # sudo: these are fixtures. marin gates product.template.standard_price
        # with write_groups, so building them as the suite's deliberately
        # under-privileged accounting user dies in setUpClass wherever it is
        # installed. Access is exercised by the tests, not by the setup.
        cls.ProductProduct = cls.env["product.product"].sudo()
        cls.Partner = cls.env["res.partner"]

        cls.vehicle_product = cls.ProductProduct.create(
            {
                "name": "Test Truck",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
            }
        )
        cls.fuel_product = cls.ProductProduct.create(
            {
                "name": "Gasoline",
                "type": "service",
                "standard_price": 1.25,
            }
        )
        cls.maintenance_product = cls.ProductProduct.create(
            {
                "name": "Oil Change",
                "type": "service",
                "standard_price": 45.00,
            }
        )
        cls.vehicle = cls.ProductTrace.create(
            {
                "name": "TRUCK-001",
                "product_id": cls.vehicle_product.id,
                "company_id": cls.test_company.id,
            }
        )
        cls.fuel_vendor = cls.Partner.create(
            {
                "name": "Gas Station",
                "is_company": True,
            }
        )
        cls.service_vendor = cls.Partner.create(
            {
                "name": "Auto Repair Shop",
                "is_company": True,
            }
        )

    def _bill_vals(self, partner, invoice_date="2024-01-15"):
        return {
            "move_type": "in_invoice",
            "partner_id": partner.id,
            "invoice_date": invoice_date,
            "journal_id": self.purchase_journal.id,
            "company_id": self.test_company.id,
        }

    def test_bill_count_single_bill(self):
        move = self.AccountMove.create(self._bill_vals(self.fuel_vendor))
        self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 60.0,
                "price_unit": 1.25,
            }
        )

        self.vehicle.asset_id._compute_move_ids()

        self.assertEqual(self.vehicle.asset_id.count_bill, 1)
        self.assertIn(move, self.vehicle.asset_id.account_move_ids)

    def test_bill_count_refreshes_without_manual_recompute(self):
        self.assertEqual(self.vehicle.asset_id.count_bill, 0)

        move = self.AccountMove.create(self._bill_vals(self.fuel_vendor))
        self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 60.0,
                "price_unit": 1.25,
            }
        )

        self.assertEqual(self.vehicle.asset_id.count_bill, 1)
        self.assertIn(move, self.vehicle.asset_id.account_move_ids)

    def test_bill_count_multiple_bills(self):
        move1 = self.AccountMove.create(self._bill_vals(self.fuel_vendor))
        self.AccountMoveLine.create(
            {
                "move_id": move1.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 60.0,
                "price_unit": 1.25,
            }
        )

        move2 = self.AccountMove.create(
            self._bill_vals(self.service_vendor, invoice_date="2024-01-20")
        )
        self.AccountMoveLine.create(
            {
                "move_id": move2.id,
                "product_id": self.maintenance_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 1.0,
                "price_unit": 45.00,
            }
        )

        self.vehicle.asset_id._compute_move_ids()

        self.assertEqual(self.vehicle.asset_id.count_bill, 2)
        self.assertIn(move1, self.vehicle.asset_id.account_move_ids)
        self.assertIn(move2, self.vehicle.asset_id.account_move_ids)

    def test_bill_count_multi_line_bill(self):
        move = self.AccountMove.create(self._bill_vals(self.service_vendor))
        self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 50.0,
                "price_unit": 1.25,
            }
        )
        self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.maintenance_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 1.0,
                "price_unit": 45.00,
            }
        )

        self.vehicle.asset_id._compute_move_ids()

        self.assertEqual(self.vehicle.asset_id.count_bill, 1)
        self.assertIn(move, self.vehicle.asset_id.account_move_ids)

    def test_cancelled_bills_excluded(self):
        move = self.AccountMove.create(self._bill_vals(self.fuel_vendor))
        self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 60.0,
                "price_unit": 1.25,
            }
        )

        self.vehicle.asset_id._compute_move_ids()
        self.assertEqual(self.vehicle.asset_id.count_bill, 1)

        move.action_cancel()

        self.vehicle.asset_id._compute_move_ids()

        self.assertEqual(self.vehicle.asset_id.count_bill, 0)

    def test_action_view_bills(self):
        move1 = self.AccountMove.create(self._bill_vals(self.fuel_vendor))
        self.AccountMoveLine.create(
            {
                "move_id": move1.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 60.0,
                "price_unit": 1.25,
            }
        )

        self.vehicle.asset_id._compute_move_ids()

        action = self.vehicle.action_view_bills()
        self.assertEqual(
            action["domain"], [("id", "in", self.vehicle.asset_id.account_move_ids.ids)]
        )
        view_types = [v[1] for v in action["views"]]
        self.assertIn("list", view_types)
        self.assertIn("form", view_types)

    def test_no_bills_for_asset_without_accounting_access(self):
        move = self.AccountMove.create(self._bill_vals(self.fuel_vendor))
        self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 60.0,
                "price_unit": 1.25,
            }
        )

        restricted_user = self.env["res.users"].create(
            {
                "name": "Restricted User",
                "login": "restricted_no_accounting",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            },
        )

        self.assertEqual(self.vehicle.asset_id.count_bill, 1)

        vehicle = self.vehicle.with_user(restricted_user)
        self.assertEqual(vehicle.asset_id.count_bill, 0)
        self.assertFalse(vehicle.asset_id.account_move_ids)

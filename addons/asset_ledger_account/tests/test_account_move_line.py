from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAccountMoveLine(AccountTestInvoicingCommon):
    chart_template = "generic_coa"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("asset_ledger.group_asset_manager")

        cls.test_company = cls.company_data["company"]
        cls.expense_account = cls.company_data["default_account_expense"]
        cls.payable_account = cls.company_data["default_account_payable"]
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
        cls.ProductAssetLog = cls.env["resource.log"]
        # sudo: these are fixtures. marin gates product.template.standard_price
        # with write_groups, so building them as the suite's deliberately
        # under-privileged accounting user dies in setUpClass wherever it is
        # installed. Access is exercised by the tests, not by the setup.
        cls.ProductProduct = cls.env["product.product"].sudo()
        cls.Partner = cls.env["res.partner"]

        cls.vehicle_product = cls.ProductProduct.create(
            {
                "name": "Test Vehicle",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("resource.kind_vehicle").id,
            }
        )
        cls.fuel_product = cls.ProductProduct.create(
            {
                "name": "Diesel Fuel",
                "type": "service",
                "standard_price": 1.50,
            }
        )
        cls.vehicle = cls.ProductTrace.create(
            {
                "name": "VH-001",
                "product_id": cls.vehicle_product.id,
                "company_id": cls.test_company.id,
            }
        )
        cls.other_vehicle = cls.ProductTrace.create(
            {
                "name": "VH-002",
                "product_id": cls.vehicle_product.id,
                "company_id": cls.test_company.id,
            }
        )
        cls.vendor = cls.Partner.create(
            {
                "name": "Test Vendor",
                "is_company": True,
            }
        )

    def _bill_vals(self, move_type="in_invoice"):
        return {
            "move_type": move_type,
            "partner_id": self.vendor.id,
            "invoice_date": "2024-01-15",
            "journal_id": self.purchase_journal.id,
            "company_id": self.test_company.id,
        }

    def test_asset_id_field_exists(self):
        move = self.AccountMove.create(self._bill_vals())
        line = self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 50.0,
                "price_unit": 1.50,
            }
        )
        self.assertEqual(line.asset_id, self.vehicle.asset_id)
        self.assertEqual(line.trace_id, self.vehicle)

    def test_analytic_distribution_with_asset(self):
        analytic_plan = self.env["account.analytic.plan"].create(
            {"name": "Test Plan for Asset"},
        )
        analytic_account = self.env["account.analytic.account"].create(
            {"name": "Vehicle Costs", "plan_id": analytic_plan.id},
        )
        self.env["account.analytic.distribution.model"].create(
            {
                "asset_id": self.vehicle.asset_id.id,
                "analytic_distribution": {str(analytic_account.id): 100},
            },
        )
        move = self.AccountMove.create(self._bill_vals())
        line = self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 50.0,
                "price_unit": 1.50,
            }
        )
        self.assertEqual(
            line.analytic_distribution,
            {str(analytic_account.id): 100},
            "asset_id was not propagated into the distribution-model search",
        )

    def test_asset_log_cleanup_on_write(self):
        move = self.AccountMove.create(self._bill_vals())
        line = self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 50.0,
                "price_unit": 1.50,
            }
        )

        log = line.asset_log_ids
        self.assertTrue(log)

        line.write({"asset_id": False})

        self.assertFalse(log.exists())

    def test_asset_log_follows_reassignment(self):
        move = self.AccountMove.create(self._bill_vals())
        line = self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 50.0,
                "price_unit": 1.50,
            }
        )
        log = line.asset_log_ids
        self.assertEqual(len(log), 1)

        line.write({"asset_id": self.other_vehicle.asset_id.id})

        self.assertEqual(line.asset_log_ids, log)
        self.assertEqual(log.trace_id, self.other_vehicle)
        self.assertFalse(
            self.ProductAssetLog.search_count([("trace_id", "=", self.vehicle.id)])
        )

    def test_asset_log_cleanup_on_unlink(self):
        move = self.AccountMove.create(self._bill_vals())
        line = self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 50.0,
                "price_unit": 1.50,
            }
        )

        log = line.asset_log_ids
        self.assertTrue(log)

        line.unlink()

        self.assertFalse(log.exists())

    def test_prepare_asset_log_values(self):
        move = self.AccountMove.create(self._bill_vals())
        line = self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 50.0,
                "price_unit": 1.50,
            }
        )

        vals = line._prepare_asset_log()

        self.assertEqual(vals["asset_id"], self.vehicle.asset_id.id)
        self.assertEqual(vals["vendor_id"], self.vendor.id)
        self.assertEqual(vals["product_id"], self.fuel_product.id)
        self.assertEqual(vals["account_move_line_id"], line.id)

    def test_refund_line_logs_a_credit_on_the_asset(self):
        refund = self.AccountMove.create(self._bill_vals(move_type="in_refund"))
        line = self.AccountMoveLine.create(
            {
                "move_id": refund.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 10.0,
                "price_unit": 1.50,
            }
        )

        self.assertTrue(
            line.asset_log_ids,
            "A credit note writes to the asset ledger too, or a reversed bill "
            "leaves its gross cost on the asset forever",
        )
        self.assertLess(line.balance, 0.0)
        self.assertEqual(line.asset_log_ids.amount, line.balance)

    def test_reversing_a_bill_nets_the_asset_ledger_to_zero(self):
        move = self.AccountMove.create(self._bill_vals())
        self.AccountMoveLine.create(
            {
                "move_id": move.id,
                "product_id": self.fuel_product.id,
                "account_id": self.expense_account.id,
                "asset_id": self.vehicle.asset_id.id,
                "quantity": 10.0,
                "price_unit": 1.50,
            }
        )
        move.action_post()
        logs = self.ProductAssetLog.search([("trace_id", "=", self.vehicle.id)])
        self.assertEqual(sum(logs.mapped("amount")), 15.0)

        move._reverse_moves([{"invoice_date": "2024-01-20"}], cancel=True)

        logs = self.ProductAssetLog.search([("trace_id", "=", self.vehicle.id)])
        self.assertEqual(len(logs), 2)
        self.assertEqual(
            sum(logs.mapped("amount")),
            0.0,
            "A fully reversed bill costs the asset nothing",
        )

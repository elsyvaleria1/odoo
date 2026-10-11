from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.test_account_move_line_tax_details import (
    TestAccountTaxDetailsReport,
)


@tagged("post_install", "-at_install")
class TestAccountFleet(TestAccountTaxDetailsReport):
    def test_tax_report_with_vehicle_split_repartition(self):
        """Test tax report with split repartition lines across different vehicles."""
        # Ensure user has access to fleet vehicles
        self.env.user.group_ids += self.env.ref(
            "resource_asset_vehicle.fleet_group_manager"
        )
        cars = self.env["resource.resource"].create(
            [
                {
                    "name": "Car 1",
                    "kind_id": self.env.ref("base.kind_vehicle").id,
                },
                {
                    "name": "Car 2",
                    "kind_id": self.env.ref("base.kind_vehicle").id,
                },
            ]
        )

        expense_account = self.company_data["default_account_expense"]
        asset_account = self.company_data["default_account_deferred_expense"]

        tax = self.env["account.tax"].create(
            {
                "name": "Split Tax",
                "amount": 10,
                "invoice_repartition_line_ids": [
                    Command.create({"repartition_type": "base", "factor_percent": 100}),
                    Command.create(
                        {
                            "repartition_type": "tax",
                            "factor_percent": 50,
                            "account_id": expense_account.id,
                        }
                    ),
                    Command.create(
                        {
                            "repartition_type": "tax",
                            "factor_percent": 50,
                            "account_id": asset_account.id,
                        }
                    ),
                ],
                "refund_repartition_line_ids": [
                    Command.create({"repartition_type": "base", "factor_percent": 100}),
                    Command.create(
                        {
                            "repartition_type": "tax",
                            "factor_percent": 50,
                            "account_id": expense_account.id,
                        }
                    ),
                    Command.create(
                        {
                            "repartition_type": "tax",
                            "factor_percent": 50,
                            "account_id": asset_account.id,
                        }
                    ),
                ],
            }
        )

        bill = self.init_invoice("in_invoice", invoice_date="2025-10-16", post=False)
        bill.write(
            {
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "account_id": expense_account.id,
                            "price_unit": 100,
                            "tax_ids": [Command.set(tax.ids)],
                            "asset_id": cars[0].id,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "account_id": expense_account.id,
                            "price_unit": 100,
                            "tax_ids": [Command.set(tax.ids)],
                            "asset_id": cars[1].id,
                        }
                    ),
                ]
            }
        )
        bill.action_post()

        tax_details = self._get_tax_details()
        self.assertEqual(len(tax_details), 2)
        for line in tax_details:
            self.assertEqual(line["tax_amount"], 5)

from odoo.fields import Command

from odoo.addons.crm.tests.common import TestCrmCommon


class TestCrmSubscription(TestCrmCommon):
    def test_crm_sale_subscription_revenue(self):
        product1, product2, recurring_product1, recurring_product2 = self.env[
            "product.template"
        ].create(
            [
                {
                    "name": "Test product1",
                    "list_price": 100.0,
                },
                {
                    "name": "Test product2",
                    "list_price": 200.0,
                },
                {
                    "name": "Recurring product1",
                    "type": "service",
                    "recurring_invoice": True,
                    "list_price": 10.0,
                },
                {
                    "name": "Recurring product2",
                    "type": "service",
                    "recurring_invoice": True,
                    "list_price": 20.0,
                },
            ]
        )

        subscription_plan = self.env["sale.subscription.plan"].create(
            {
                "name": "Monthly",
                "repeat_interval": 1,
                "repeat_unit": "month",
                "sequence": 4,
            }
        )

        crm_recurring_plan = self.env["crm.recurring.plan"].create(
            {
                "name": "Test yearly plan",
                "number_of_months": 12,
            }
        )

        my_pricelist = self.env["product.pricelist"].create(
            {"name": "Rupee", "currency_id": self.ref("base.INR")}
        )
        pricelist_expected_by_lead = self.env["product.pricelist"].create(
            {"name": "Rupee", "currency_id": self.ref("base.USD")}
        )

        so_values = {
            "partner_id": self.env.user.partner_id.id,
            "opportunity_id": self.lead_1.id,
            "plan_id": subscription_plan.id,
        }
        so1, so2 = self.env["sale.order"].create(
            [
                {
                    **so_values,
                    "pricelist_id": my_pricelist.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": product.product_variant_id.id,
                            }
                        )
                        for product in [product1, recurring_product1]
                    ],
                },
                {
                    **so_values,
                    "pricelist_id": pricelist_expected_by_lead.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": product.product_variant_id.id,
                            }
                        )
                        for product in [product2, recurring_product2]
                    ],
                },
            ]
        )

        self.env.user.group_ids = [
            Command.set(self.env.ref("crm.group_use_recurring_revenues").ids)
        ]
        self.assertEqual(self.lead_1.expected_revenue, 0)
        self.assertFalse(self.lead_1.recurring_plan)

        so1.action_confirm()
        self.assertEqual(self.lead_1.expected_revenue, 0)
        self.assertEqual(self.lead_1.recurring_revenue, 0)
        so2.action_confirm()
        self.assertEqual(
            self.lead_1.recurring_plan.id, self.ref("crm.crm_recurring_plan_monthly")
        )
        self.assertEqual(self.lead_1.recurring_revenue, 20)
        self.assertEqual(self.lead_1.expected_revenue, 200)

        self.lead_1.write(
            {
                "recurring_plan": crm_recurring_plan,
                "recurring_revenue": 0,
                "expected_revenue": 0,
            }
        )
        so2._action_cancel()
        so2.action_draft()
        so2.action_confirm()
        self.assertEqual(self.lead_1.expected_revenue, 200)
        self.assertEqual(self.lead_1.recurring_revenue, 240)

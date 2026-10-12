from odoo.tests.common import tagged, users, warmup

from odoo.addons.sale_subscription.tests.common_sale_subscription import (
    TestSubscriptionCommon,
)


@tagged("sub_perf", "post_install", "-at_install")
class TestSubscriptionPerformance(TestSubscriptionCommon):
    @users("__system__")
    @warmup
    def test_recurring_order_creation_perf(self):
        ORDER_COUNT = 100
        partners = self.env["res.partner"].create(
            [
                {
                    "name": "Jean-Luc %s" % (idx),
                    "email": "jean-luc-%s@opoo.com" % (idx),
                    "user_id": self.env.user.id,
                }
                for idx in range(ORDER_COUNT)
            ]
        )
        with self.assertQueryCount(__system__=2885):
            sale_orders = self.env["sale.order"].create(
                [
                    {
                        "name": "SO %s" % idx,
                        "partner_id": partners[idx].id,
                        "plan_id": self.plan_month.id,
                        "line_ids": [
                            (
                                0,
                                0,
                                {
                                    "name": self.company_data[
                                        "product_order_cost"
                                    ].name,
                                    "product_id": self.product.id,
                                    "product_qty": 2,
                                    "qty_transferred": 1,
                                    "product_uom_id": self.company_data[
                                        "product_order_cost"
                                    ].uom_id.id,
                                    "price_unit": self.company_data[
                                        "product_order_cost"
                                    ].list_price,
                                },
                            ),
                            (
                                0,
                                0,
                                {
                                    "name": self.company_data[
                                        "product_delivery_cost"
                                    ].name,
                                    "product_id": self.product.id,
                                    "product_qty": 4,
                                    "qty_transferred": 1,
                                    "product_uom_id": self.company_data[
                                        "product_delivery_cost"
                                    ].uom_id.id,
                                    "price_unit": self.company_data[
                                        "product_delivery_cost"
                                    ].list_price,
                                },
                            ),
                        ],
                    }
                    for idx in range(ORDER_COUNT)
                ]
            )

            sale_orders.action_confirm()

        product_tmpl = self.env["product.template"].create(
            {
                "name": "Non recurring Product",
                "type": "service",
                "uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        product_id = product_tmpl.product_variant_id
        NR_COUNT = 25
        self.env["sale.order"].create(
            [
                {
                    "name": "SO %s" % idx,
                    "partner_id": partners[idx].id,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": self.company_data["product_order_cost"].name,
                                "product_id": product_id.id,
                                "product_qty": 2,
                                "qty_transferred": 1,
                                "product_uom_id": self.company_data[
                                    "product_order_cost"
                                ].uom_id.id,
                                "price_unit": self.company_data[
                                    "product_order_cost"
                                ].list_price,
                            },
                        ),
                    ],
                }
                for idx in range(NR_COUNT)
            ]
        )

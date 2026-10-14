from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import Form

from odoo.addons.stock.tests.common import TestStockCommon


class TestStockReplenish(TestStockCommon):
    def test_base_delay(self):
        far_warehouse = self.env["stock.warehouse"].create(
            {"name": "Far away", "code": "FAR"}
        )

        def pull(warehouse, delay):
            return Command.create(
                {
                    "name": f"buy into {warehouse.code}",
                    "location_src_id": self.supplier_location.id,
                    "location_dest_id": warehouse.lot_stock_id.id,
                    "warehouse_id": warehouse.id,
                    "company_id": self.env.company.id,
                    "action": "pull",
                    "procure_method": "make_to_stock",
                    "picking_type_id": warehouse.in_type_id.id,
                    "delay": delay,
                }
            )

        route_no_delay, route_delay = self.env["stock.route"].create(
            [
                {
                    "name": "no delay",
                    "product_selectable": True,
                    "rule_ids": [pull(self.warehouse_1, 0)],
                },
                {
                    "name": "delay",
                    "product_selectable": True,
                    "rule_ids": [pull(self.warehouse_1, 2), pull(far_warehouse, 30)],
                },
            ]
        )

        with freeze_time("2023-01-01"):
            wizard = Form(
                self.env["wizard.product.product.replenish"].with_context(
                    default_product_id=self.productA.id,
                    default_product_tmpl_id=self.productA.product_tmpl_id.id,
                )
            )
            wizard.warehouse_id = self.warehouse_1
            wizard.route_id = route_no_delay
            self.assertEqual(
                fields.Datetime.from_string("2023-01-01 00:00:00"),
                wizard._values["date_planned"],
            )
            wizard.route_id = route_delay
            self.assertEqual(
                fields.Datetime.from_string("2023-01-03 00:00:00"),
                wizard._values["date_planned"],
                "only the chain into the chosen warehouse delays the replenishment",
            )

    def test_replenish_no_routes(self):
        product = self.env["product.template"].create(
            {
                "name": "Brand new product",
                "is_storable": True,
            }
        )
        self.assertEqual(len(product.route_ids), 0)
        wizard = Form(
            self.env["wizard.product.product.replenish"].with_context(
                default_product_tmpl_id=product.id
            )
        )
        self.assertEqual(wizard._values["quantity"], 1)

    def test_replenish_notifies_the_replenished_product(self):
        warehouse = self.warehouse_1
        route = self.env["stock.route"].create(
            {
                "name": "unit-replenish-route",
                "product_selectable": True,
                "rule_ids": [
                    Command.create(
                        {
                            "name": "receive",
                            "action": "pull",
                            "auto": "manual",
                            "location_src_id": self.supplier_location.id,
                            "location_dest_id": warehouse.lot_stock_id.id,
                            "picking_type_id": self.picking_type_in.id,
                            "procure_method": "make_to_stock",
                            "company_id": warehouse.company_id.id,
                        }
                    )
                ],
            }
        )
        product_a, product_b = self.env["product.product"].create(
            [
                {
                    "name": "Repl-A",
                    "is_storable": True,
                    "route_ids": [Command.set(route.ids)],
                },
                {
                    "name": "Repl-B",
                    "is_storable": True,
                    "route_ids": [Command.set(route.ids)],
                },
            ]
        )

        wizard = self.env["wizard.product.product.replenish"].create(
            {
                "product_id": product_a.id,
                "product_tmpl_id": product_a.product_tmpl_id.id,
                "product_uom_id": product_a.uom_id.id,
                "quantity": 7,
                "warehouse_id": warehouse.id,
                "route_id": route.id,
                "date_planned": self.env.cr.now(),
            }
        )

        self.env["stock.move"].create(
            {
                "product_id": product_b.id,
                "product_uom_qty": 99,
                "company_id": warehouse.company_id.id,
                "date": self.env.cr.now(),
                "procure_method": "make_to_stock",
                "location_id": self.supplier_location.id,
                "location_dest_id": warehouse.lot_stock_id.id,
            }
        )
        self.env.flush_all()

        now = self.env.cr.now()
        wizard.action_replenish()
        notified = wizard._get_record_to_notify(now)

        self.assertTrue(notified, "a move should have been created and notified")
        self.assertEqual(
            notified.product_id,
            product_a,
            "the notification must point at the replenished product, not an "
            "unrelated move sharing the transaction timestamp",
        )
        self.assertEqual(notified.product_uom_qty, 7)

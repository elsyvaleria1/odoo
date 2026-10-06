from odoo import Command
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account_collection.tests.common import CollectionCommon
from odoo.addons.stock_fleet_trace.tests.common import TripFixtureMixin


class SuperuserFixtures:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(su=True)


@tagged("post_install", "-at_install")
class TestVanHandOver(TripFixtureMixin, SuperuserFixtures, CollectionCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.seller = new_test_user(
            cls.env,
            login="van_seller",
            groups="base.group_user,sale.group_sale_salesman,"
            "account_collection.group_collection_collector",
            company_id=cls.env.company.id,
            company_ids=[Command.set(cls.env.company.ids)],
        )
        cls.seller_employee = cls.env["hr.employee"].create(
            {"name": "Van seller", "user_id": cls.seller.id}
        )
        cls.out_type.auto_batch = False
        cls.product.write(
            {"list_price": 100.0, "invoice_policy": "ordered", "taxes_id": False}
        )

    def _order(self, quantity):
        order = (
            self.env["sale.order"]
            .with_user(self.seller)
            .create(
                {
                    "partner_id": self.partner_a.id,
                    "user_id": self.seller.id,
                    "warehouse_id": self.warehouse.id,
                    "payment_term_id": self.env.ref(
                        "payment_term.account_payment_term_immediate"
                    ).id,
                    "line_ids": [
                        Command.create(
                            {"product_id": self.product.id, "product_qty": quantity}
                        )
                    ],
                }
            )
        )
        order.action_confirm()
        return order

    def _hand_over(self, order):
        action = order.action_open_cash_collect()
        wizard = Form(
            self.env[action["res_model"]]
            .with_user(self.seller)
            .with_context(**action["context"])
        )
        wizard.hand_over = True
        wizard.save().action_collect()

    def _van_trip(self, free):
        trip = self._trip(self._delivery(5), operator=self.seller_employee)
        trip._trip_load_free_stock([(self.product, free)])
        trip.action_depart()
        return trip

    def test_a_cash_sale_on_the_route_leaves_from_the_vehicle(self):
        trip = self._van_trip(free=10)
        order = self._order(3)

        self._hand_over(order)

        picking = order.picking_ids
        self.assertEqual(picking.state, "done")
        self.assertIn(picking.location_id, trip.trip_location_ids)
        self.assertEqual(self._on_board(trip, self.product), 12)
        self.assertEqual(picking.move_ids.trip_batch_id, trip)

    def test_without_stock_on_the_vehicle_it_leaves_from_the_warehouse(self):
        trip = self._van_trip(free=1)
        order = self._order(3)

        self._hand_over(order)

        picking = order.picking_ids
        self.assertEqual(picking.state, "done")
        self.assertNotIn(picking.location_id, trip.trip_location_ids)
        self.assertEqual(self._on_board(trip, self.product), 6)

    def _on_board(self, trip, product):
        quants = self.env["stock.quant"].search(
            [
                ("location_id", "in", trip.trip_location_ids.ids),
                ("product_id", "=", product.id),
            ]
        )
        return sum(quants.mapped("quantity"))

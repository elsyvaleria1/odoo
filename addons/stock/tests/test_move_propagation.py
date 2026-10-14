from datetime import datetime, timedelta

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMovePropagation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock = cls.warehouse.lot_stock_id
        cls.supplier = cls.env.ref("stock.stock_location_suppliers")
        cls.customer = cls.env.ref("stock.stock_location_customers")

    def _product(self, name):
        return self.env["product.product"].create({"name": name, "is_storable": True})

    def _receipt(self, products, destination=None):
        destination = destination or self.stock
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.in_type_id.id,
                "location_id": self.supplier.id,
                "location_dest_id": destination.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": 5,
                            "location_id": self.supplier.id,
                            "location_dest_id": destination.id,
                        },
                    )
                    for product in products
                ],
            }
        )
        picking.action_confirm()
        return picking

    def test_a_type_default_does_not_move_an_open_move(self):
        shelf = self.env["stock.location"].create(
            {"name": "Shelf-X", "location_id": self.stock.id}
        )
        dock = self.env["stock.location"].create(
            {"name": "Dock-Y", "location_id": self.warehouse.view_location_id.id}
        )
        move = self._receipt(self._product("Kept")).move_ids
        move.location_dest_id = shelf

        self.warehouse.in_type_id.default_location_dest_id = dock

        self.assertEqual(move.location_dest_id, shelf)
        self.assertEqual(move.move_line_ids.location_dest_id, shelf)

    def test_a_type_code_change_does_not_move_an_open_move(self):
        shelf = self.env["stock.location"].create(
            {"name": "Shelf-B", "location_id": self.stock.id}
        )
        move = self._receipt(self._product("Code")).move_ids
        move.location_dest_id = shelf

        self.warehouse.in_type_id.write({"code": "internal"})

        self.assertEqual(move.location_dest_id, shelf)
        self.assertEqual(move.move_line_ids.location_dest_id, shelf)

    def test_rewriting_a_deadline_keeps_the_chain_deadlines(self):
        product = self._product("Deadline")
        out_zone = self.env["stock.location"].create(
            {"name": "OutZone", "location_id": self.warehouse.view_location_id.id}
        )
        head = self.env["stock.move"].create(
            {
                "product_id": product.id,
                "product_uom_qty": 1,
                "location_id": self.stock.id,
                "location_dest_id": out_zone.id,
            }
        )
        tail = self.env["stock.move"].create(
            {
                "product_id": product.id,
                "product_uom_qty": 1,
                "location_id": out_zone.id,
                "location_dest_id": self.customer.id,
                "move_orig_ids": [(4, head.id)],
            }
        )
        (head | tail)._action_confirm(merge=False)
        own = {"date_deadline_propagate_ids": {head.id, tail.id}}
        head.with_context(**own).date_deadline = datetime(2026, 11, 1, 12)
        tail.with_context(**own).date_deadline = datetime(2026, 11, 5, 12)

        head.write({"date_deadline": head.date_deadline})
        self.assertEqual(tail.date_deadline, datetime(2026, 11, 5, 12))

        head.write({"date_deadline": datetime(2026, 11, 2, 12)})
        self.assertEqual(
            tail.date_deadline, datetime(2026, 11, 5, 12) + timedelta(days=1)
        )

    def test_clearing_an_empty_deadline_keeps_the_chain_deadlines(self):
        product = self._product("No deadline")
        head, tail = self.env["stock.move"].create(
            [
                {
                    "product_id": product.id,
                    "product_uom_qty": 1,
                    "location_id": self.stock.id,
                    "location_dest_id": self.customer.id,
                },
                {
                    "product_id": product.id,
                    "product_uom_qty": 1,
                    "location_id": self.stock.id,
                    "location_dest_id": self.customer.id,
                },
            ]
        )
        tail.move_orig_ids = head
        (head | tail)._action_confirm(merge=False)
        tail.with_context(
            date_deadline_propagate_ids={head.id, tail.id}
        ).date_deadline = datetime(2026, 11, 5, 12)

        head.write({"date_deadline": False})

        self.assertEqual(tail.date_deadline, datetime(2026, 11, 5, 12))

    def test_pushing_packed_moves_reads_packages_once(self):
        self.warehouse.reception_steps = "two_steps"
        input_location = self.warehouse.in_type_id.default_location_dest_id
        receipts = []
        for size in (3, 3, 12):
            receipt = self._receipt(
                [self._product(f"Packed {size}-{i}") for i in range(size)],
                destination=input_location,
            )
            for line in receipt.move_line_ids:
                line.result_package_id = self.env["stock.package"].create(
                    {"name": f"PAL-{line.id}"}
                )
            receipt.move_ids.picked = True
            receipts.append(receipt)
        pending = iter(receipts)

        def validate(size):
            receipt = next(pending)
            self.assertEqual(len(receipt.move_ids), size)
            receipt._action_done()
            self.assertEqual(
                len(receipt.move_ids.move_dest_ids), size, "each move is pushed"
            )

        self.assertQueriesConstant(validate, small=3, large=12)

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPackageLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock = cls.warehouse.lot_stock_id
        cls.supplier = cls.env.ref("stock.stock_location_suppliers")
        cls.customer = cls.env.ref("stock.stock_location_customers")

    def _product(self, name, **vals):
        return self.env["product.product"].create(
            {"name": name, "is_storable": True, **vals}
        )

    def _transfer(self, picking_type, source, destination, quantities):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": quantity,
                            "location_id": source.id,
                            "location_dest_id": destination.id,
                        },
                    )
                    for product, quantity in quantities
                ],
            }
        )
        picking.action_confirm()
        return picking

    def _receipt(self, *quantities):
        return self._transfer(
            self.warehouse.in_type_id, self.supplier, self.stock, quantities
        )

    def test_a_received_nested_box_can_leave_its_pallet_alone(self):
        box_product, other_product = self._product("In C"), self._product("In D")
        receipt = self._receipt((box_product, 3), (other_product, 3))
        receipt.move_ids.picked = True
        line_c = receipt.move_ids.filtered(
            lambda m: m.product_id == box_product
        ).move_line_ids
        line_d = receipt.move_line_ids - line_c
        line_c.action_put_in_pack(package_name="BOX-C")
        line_d.action_put_in_pack(package_name="BOX-D")
        box_c, box_d = line_c.result_package_id, line_d.result_package_id
        pallet = self.env["stock.package"].create({"name": "PALLET-G"})
        (box_c | box_d).action_put_in_pack(package_id=pallet.id)
        receipt.button_validate()
        self.assertFalse(
            box_c.package_dest_id, "a received package keeps no pending container"
        )

        delivery = self._transfer(
            self.warehouse.out_type_id, self.stock, self.customer, [(box_product, 3)]
        )
        delivery.action_assign()
        delivery.move_ids.picked = True
        delivery.button_validate()

        self.assertEqual(delivery.state, "done")
        self.assertFalse(box_c.parent_package_id)
        self.assertEqual(pallet.child_package_ids, box_d)

    def test_receiving_into_a_box_keeps_it_on_its_pallet(self):
        stored, received = self._product("Stored"), self._product("Received")
        pallet = self.env["stock.package"].create({"name": "PALLET"})
        box = self.env["stock.package"].create({"name": "BOX"})
        self.env["stock.quant"].with_context(
            inventory_mode=True
        )._update_available_quantity(stored, self.stock, 5, package_id=box)
        box.parent_package_id = pallet

        receipt = self._receipt((received, 3))
        receipt.move_ids.move_line_ids.result_package_id = box
        receipt.move_ids.picked = True
        receipt.button_validate()

        self.assertEqual(box.parent_package_id, pallet)
        self.assertEqual(
            set(pallet.contained_quant_ids.mapped("product_id").ids),
            {stored.id, received.id},
        )

    def test_a_validated_package_history_names_only_its_own_transfer(self):
        product = self._product("History")
        box = self.env["stock.package"].create({"name": "BOX-H"})
        first, second = self._receipt((product, 3)), self._receipt((product, 3))
        for receipt in first | second:
            receipt.move_ids.move_line_ids.result_package_id = box
            receipt.move_ids.picked = True

        first.button_validate()

        history = self.env["stock.package.history"].search(
            [("package_id", "=", box.id)]
        )
        self.assertEqual(history.picking_ids, first)
        self.assertFalse(second.move_line_ids.package_history_id)

    def test_two_products_may_share_a_new_serial_name(self):
        products = self._product("Ser A", tracking="serial") | self._product(
            "Ser B", tracking="serial"
        )
        receipt = self._receipt(*((product, 1) for product in products))
        for move in receipt.move_ids:
            move.move_line_ids.lot_name = "SN-SHARED"
        receipt.move_ids.picked = True
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")
        self.assertEqual(
            receipt.move_line_ids.trace_id.product_id, products, "one lot each"
        )

    def test_one_product_still_refuses_a_repeated_serial(self):
        product = self._product("Ser C", tracking="serial")
        receipt = self._receipt((product, 2))
        receipt.move_ids.move_line_ids.unlink()
        self.env["stock.move.line"].create(
            [
                {
                    "move_id": receipt.move_ids.id,
                    "picking_id": receipt.id,
                    "product_id": product.id,
                    "quantity": 1,
                    "lot_name": "SN-TWICE",
                    "location_id": self.supplier.id,
                    "location_dest_id": self.stock.id,
                }
            ]
            * 2
        )
        receipt.move_ids.picked = True
        with self.assertRaises(ValidationError):
            receipt.button_validate()

    def test_the_slip_counts_a_backorder_once_per_product(self):
        product = self._product("Slip")
        self.env["stock.quant"].with_context(
            inventory_mode=True
        )._update_available_quantity(product, self.stock, 100)
        delivery = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.out_type_id.id,
                "location_id": self.stock.id,
                "location_dest_id": self.customer.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": 10,
                            "price_unit": price,
                            "location_id": self.stock.id,
                            "location_dest_id": self.customer.id,
                        },
                    )
                    for price in (1, 2)
                ],
            }
        )
        delivery.action_confirm()
        self.assertEqual(len(delivery.move_ids), 2)
        delivery.action_assign()
        delivery.move_ids.move_line_ids.quantity = 4
        delivery.move_ids.picked = True
        delivery._action_done()

        aggregated = delivery.move_line_ids._get_aggregated_product_quantities()
        self.assertEqual(
            [values["qty_ordered"] for values in aggregated.values()], [20.0]
        )

    def test_removing_a_container_from_one_transfer_leaves_the_others(self):
        self.env.user.group_ids |= self.env.ref("stock.group_stock_multi_locations")
        rack = self.env["stock.location"].create(
            {"name": "Rack", "location_id": self.stock.id}
        )
        pallet_type = self.env["stock.package.type"].create({"name": "Pallet"})
        self.env["stock.putaway.rule"].create(
            {
                "location_in_id": self.stock.id,
                "location_out_id": rack.id,
                "package_type_ids": [(6, 0, pallet_type.ids)],
            }
        )
        first = self._receipt((self._product("Removed A"), 2))
        second = self._receipt((self._product("Removed B"), 2))
        first.move_line_ids.action_put_in_pack(package_name="BOX-A")
        second.move_line_ids.action_put_in_pack(package_name="BOX-B")
        pallet = self.env["stock.package"].create(
            {"name": "PALLET-R", "package_type_id": pallet_type.id}
        )
        boxes = (
            first.move_line_ids.result_package_id
            | second.move_line_ids.result_package_id
        )
        boxes.action_put_in_pack(package_id=pallet.id)
        self.assertEqual(second.move_line_ids.location_dest_id, rack)

        pallet.with_context(picking_ids=first.ids).action_remove_package()

        self.assertFalse(first.move_line_ids.result_package_id.package_dest_id)
        self.assertEqual(second.move_line_ids.result_package_id.package_dest_id, pallet)
        self.assertEqual(second.move_line_ids.location_dest_id, rack)

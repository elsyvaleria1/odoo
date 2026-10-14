from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPickingScope(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock = cls.warehouse.lot_stock_id
        cls.customer = cls.env.ref("stock.stock_location_customers")
        cls.product = cls.env["product.product"].create(
            {"name": "Scope", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.stock, 100)

    def _delivery(self, quantity, source=None):
        source = source or self.stock
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.out_type_id.id,
                "location_id": source.id,
                "location_dest_id": self.customer.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "location_id": source.id,
                            "location_dest_id": self.customer.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        return picking

    def test_changing_the_partner_in_the_form_keeps_the_source(self):
        self.env.user.group_ids |= self.env.ref("stock.group_stock_multi_locations")
        shelf = self.env["stock.location"].create(
            {"name": "Shelf", "location_id": self.stock.id}
        )
        picking = self._delivery(2, source=shelf)
        form = Form(picking)
        form.partner_id = self.env["res.partner"].create({"name": "New partner"})
        picking = form.save()
        self.assertEqual(picking.location_id, shelf)

    def test_a_mixed_backorder_decision_keeps_the_batch(self):
        first, second = self._delivery(10), self._delivery(10)
        batch = self.env["stock.picking.batch"].create(
            {"picking_ids": [Command.set((first | second).ids)]}
        )
        batch.action_confirm()
        (first | second).move_ids.quantity = 4
        (first | second).move_ids.picked = True
        action = batch.action_done()
        wizard = (
            self.env[action["res_model"]].with_context(action["context"]).create({})
        )
        for line in wizard.backorder_confirmation_line_ids:
            line.to_backorder = line.picking_id == first
        wizard.process()

        self.assertEqual((first | second).mapped("state"), ["done", "done"])
        self.assertEqual(batch.picking_ids & (first | second), first | second)

    def test_a_return_reserves_only_what_was_reserved(self):
        picking_type = self.warehouse.pick_type_id
        self.warehouse.delivery_steps = "pick_ship"
        pick = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": self.stock.id,
                "location_dest_id": self.warehouse.wh_output_stock_loc_id.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 10,
                            "location_id": self.stock.id,
                            "location_dest_id": self.warehouse.wh_output_stock_loc_id.id,
                        }
                    )
                ],
            }
        )
        ship = self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 10,
                "location_id": self.warehouse.wh_output_stock_loc_id.id,
                "location_dest_id": self.customer.id,
                "picking_type_id": self.warehouse.out_type_id.id,
                "move_orig_ids": [Command.link(pick.move_ids.id)],
                "procure_method": "make_to_order",
            }
        )
        pick.action_confirm()
        ship._action_confirm()
        pick.action_assign()
        pick.move_ids.picked = True
        pick._action_done()
        ship._unreserve()
        self.assertEqual(ship.quantity, 0)

        wizard = (
            self.env["wizard.stock.picking.return"]
            .with_context(active_id=pick.id, active_model="stock.picking")
            .create({})
        )
        wizard.product_return_moves.quantity = 2
        wizard._create_return()

        self.assertEqual(ship.quantity, 0, "the user had unreserved it")

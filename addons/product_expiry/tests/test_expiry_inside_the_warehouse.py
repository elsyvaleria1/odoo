from odoo.fields import Command
from odoo.tests import new_test_user

from .test_expiry_audit_2026_08 import ExpiryAuditCommon


class TestExpiredGoodsInsideTheWarehouse(ExpiryAuditCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shelf = cls.env["stock.location"].create(
            {
                "name": "Expired shelf",
                "usage": "internal",
                "location_id": cls.stock_location.id,
            }
        )
        cls.branch = cls.env["stock.warehouse"].create(
            {"name": "Expiry Branch", "code": "EXB"}
        )
        cls.stock_user = new_test_user(
            cls.env, login="expiry_reshelver", groups="stock.group_stock_user"
        )

    def _expired_lot(self, name):
        lot = self._lot(name, -2)
        self.env.flush_all()
        lot.write({"removal_date": False})
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_location, 5.0, trace_id=lot
        )
        self.env.flush_all()
        return lot

    def _internal_transfer(self, *destinations):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.stock_location.id,
                "location_dest_id": destinations[0].id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 5.0,
                            "location_id": self.stock_location.id,
                            "location_dest_id": destination.id,
                        }
                    )
                    for destination in destinations
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        self.env.flush_all()
        return picking

    def test_a_stock_user_reshelves_an_expired_lot_without_a_manager(self):
        self._expired_lot("INSIDE-SHELF")
        picking = self._internal_transfer(self.shelf)
        picking.with_user(self.stock_user).button_validate()
        self.assertEqual(picking.state, "done")

    def test_sending_an_expired_lot_to_another_warehouse_still_asks(self):
        self._expired_lot("INSIDE-BRANCH")
        picking = self._internal_transfer(self.branch.lot_stock_id)
        action = picking.with_user(self.stock_user).button_validate()
        self.assertEqual(action["res_model"], "wizard.stock.picking.validate.expired")
        self.assertNotEqual(picking.state, "done")

    def test_dropping_the_expired_lines_spares_the_reshelved_ones(self):
        self._expired_lot("INSIDE-MIX-1")
        self._expired_lot("INSIDE-MIX-2")
        picking = self._internal_transfer(self.shelf, self.branch.lot_stock_id)
        self.assertEqual(len(picking.move_line_ids), 2)
        action = picking.button_validate()
        wizard = (
            self.env["wizard.stock.picking.validate.expired"]
            .with_context(**action["context"])
            .create({})
        )
        wizard.process_no_expired()
        self.assertEqual(
            picking.move_line_ids.location_dest_id,
            self.shelf,
            "only the line leaving the warehouse was asked about and dropped",
        )

from uuid import uuid4

from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import (
    CommonPosTest,
    PosCashRoundingSessionCommon,
)


@tagged("post_install", "-at_install")
class TestPosOrderLineComboShare(CommonPosTest):
    def setUp(self):
        super().setUp()
        self.pos_config_usd.open_ui()
        meal = self.ten_dollars_no_tax.product_variant_id
        side = self.twenty_dollars_no_tax.product_variant_id
        line = {"price_unit": 0, "price_subtotal": 0, "price_subtotal_incl": 0}
        self.order = self.env["pos.order"].create(
            {
                "session_id": self.pos_config_usd.current_session_id.id,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_tax": 0,
                "amount_return": 0,
                "lines": [Command.create({**line, "product_id": meal.id, "qty": 2})],
            }
        )
        self.parent = self.order.lines
        self.child = self.env["pos.order.line"].create(
            {
                **line,
                "order_id": self.order.id,
                "product_id": side.id,
                "qty": 4,
                "combo_parent_id": self.parent.id,
            }
        )

    def test_a_combo_child_stores_its_share_of_the_parent(self):
        self.assertEqual(self.child.combo_qty_per_parent, 2)
        self.assertFalse(self.parent.combo_qty_per_parent)

    def test_a_combo_at_zero_keeps_the_share_it_had(self):
        (self.parent | self.child).write({"qty": 0})
        self.env.flush_all()
        self.child.invalidate_recordset(["combo_qty_per_parent"])

        self.assertEqual(self.child.combo_qty_per_parent, 2)

    def test_the_share_follows_a_quantity_change(self):
        self.child.qty = 6

        self.assertEqual(self.child.combo_qty_per_parent, 3)

    def test_the_share_is_loaded_to_the_till(self):
        self.assertIn(
            "combo_qty_per_parent",
            self.env["pos.order.line"]._load_pos_data_fields(self.pos_config_usd),
        )


@tagged("post_install", "-at_install")
class TestPosComboShareSync(PosCashRoundingSessionCommon):
    def _line_vals(self, qty, share=False, **values):
        return {
            "uuid": str(uuid4()),
            "product_id": self.product_a.id,
            "qty": qty,
            "price_unit": 0,
            "price_subtotal": 0,
            "price_subtotal_incl": 0,
            "tax_ids": [Command.clear()],
            "combo_qty_per_parent": share,
            **values,
        }

    def _order_vals(self, lines, mapping=None):
        return {
            "uuid": str(uuid4()),
            "session_id": self.session.id,
            "state": "draft",
            "amount_tax": 0,
            "amount_total": 0,
            "amount_paid": 0,
            "amount_return": 0,
            "lines": [Command.create(vals) for vals in lines],
            "relations_uuid_mapping": {"pos.order.line": mapping or {}},
        }

    def _lines(self, vals_list):
        lines = self.env["pos.order.line"].search(
            [("uuid", "in", [vals["uuid"] for vals in vals_list])]
        )
        return lines.sorted(
            key=lambda line: [vals["uuid"] for vals in vals_list].index(line.uuid)
        )

    def test_the_till_sends_the_share_and_never_the_over_refund_flag(self):
        Session = self.env["pos.session"]

        line_fields = Session._get_field_relations(
            "pos.order.line", ["combo_qty_per_parent"]
        )
        order_fields = Session._get_field_relations("pos.order", ["is_over_refund"])

        self.assertFalse(line_fields["combo_qty_per_parent"]["compute"])
        self.assertTrue(order_fields["is_over_refund"]["compute"])

    def test_a_combo_first_synced_at_zero_keeps_the_shares_its_till_sent(self):
        parent = self._line_vals(0)
        children = [self._line_vals(0, 2), self._line_vals(0, 1)]
        mapping = {
            child["uuid"]: {"combo_parent_id": parent["uuid"]} for child in children
        }

        self.env["pos.order"].sync_from_ui(
            [self._order_vals([parent, *children], mapping)]
        )

        lines = self._lines(children)
        self.assertEqual(lines.combo_parent_id, self._lines([parent]))
        self.assertEqual(lines.mapped("combo_qty_per_parent"), [2, 1])

    def test_the_quantities_of_a_combo_outrank_a_share_the_till_sent(self):
        parent = self._line_vals(2)
        values = self._order_vals([parent])
        self.env["pos.order"].sync_from_ui([values])
        parent_line = self._lines([parent])
        child = self._line_vals(6, 2, combo_parent_id=parent_line.id)
        values["lines"] = [Command.create(child)]
        values["relations_uuid_mapping"] = {}

        self.env["pos.order"].sync_from_ui([values])

        self.assertEqual(self._lines([child]).combo_qty_per_parent, 3)

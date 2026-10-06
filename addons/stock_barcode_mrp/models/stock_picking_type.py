from odoo import fields, models
from odoo.fields import Domain


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"
    _access_verbs = {"print_mrp_barcode_sheet": models.Verb(requires="read")}

    count_mo_confirmed = fields.Integer(compute="_compute_count_mo_confirmed")

    def _compute_count_mo_confirmed(self) -> None:
        # One GROUP BY for the whole set rather than a COUNT(*) per picking
        # type, which `test_lint E8507` counts as a query inside a loop. The two
        # non-record leaves ride along in the domain unchanged.
        counts = dict(
            self.env["mrp.production"]._read_group(
                [
                    ("state", "in", ["confirmed", "progress"]),
                    ("picking_type_id", "in", self.ids),
                    ("reservation_state", "=", "assigned"),
                ],
                ["picking_type_id"],
                ["__count"],
            )
        )
        for pick_type in self:
            pick_type.count_mo_confirmed = counts.get(pick_type, 0)

    def _compute_is_barcode_picking_type(self) -> None:
        for picking_type in self:
            if picking_type.code == "mrp_operation":
                picking_type.is_barcode_picking_type = True
            else:
                super(StockPickingType, picking_type)._compute_is_barcode_picking_type()

    def action_view_pickings_ready_kanban(self):
        if self.code == "mrp_operation":
            res = self._prepare_action_by_xml_id("stock_barcode_mrp.mrp_action_kanban")
            res["domain"] = Domain.AND(
                [
                    res["domain"],
                    [("picking_type_id.active", "=", True)],
                ]
            )
            return res
        return super().action_view_pickings_ready_kanban()

    def _get_barcode_config(self):
        return super()._get_barcode_config()

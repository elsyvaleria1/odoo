from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError


class WizardStockTripScan(models.TransientModel):
    """Scan the trip sheet at the warehouse, and the slip and lots at a stop."""

    _name = "wizard.stock.trip.scan"
    _description = "Trip Scan"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        required=True,
        ondelete="cascade",
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Current Stop",
        domain="[('batch_id', '=', batch_id)]",
        help="The delivery whose slip was scanned last: lots scanned next count "
        "for it.",
    )
    code = fields.Char(help="Scan the trip sheet, a delivery slip or a lot label.")
    message = fields.Char(readonly=True)
    summary = fields.Text(compute="_compute_summary")

    @api.depends("picking_id")
    def _compute_summary(self) -> None:
        for wizard in self:
            wizard.summary = wizard.picking_id._trip_scan_summary()

    def action_scan(self) -> dict:
        self.check_singleton()
        if not self.code:
            raise UserError(self.env._("Scan or type a code first."))
        message, picking = self.batch_id._trip_process_scan(
            self.code, picking=self.picking_id
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Scan"),
            "res_model": self._name,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_batch_id": self.batch_id.id,
                "default_picking_id": picking.id,
                "default_message": message,
            },
        }


class StockPicking(models.Model):
    _inherit = "stock.picking"

    trip_scan_ids = fields.One2many(
        comodel_name="stock.trip.scan",
        inverse_name="picking_id",
        string="Scans",
    )

    def _trip_scanned_by_lot(self):
        """Units scanned at this stop, per (product, lot)."""
        self.check_singleton()
        scanned = defaultdict(float)
        # Only this trip's scans: a delivery loaded again starts its count over.
        for scan in self.trip_scan_ids.filtered(
            lambda s: s.kind == "lot" and s.batch_id == self.batch_id
        ):
            scanned[(scan.product_id, scan.trace_id)] += scan.quantity
        return scanned

    def _trip_on_board_by_lot(self):
        self.check_singleton()
        on_board = defaultdict(float)
        for line in self.move_ids.move_line_ids:
            if line.state not in ("done", "cancel"):
                on_board[(line.product_id, line.trace_id)] += line.quantity
        return on_board

    def _trip_scan_summary(self) -> str:
        if not self:
            return ""
        scanned = self._trip_scanned_by_lot()
        return "\n".join(
            f"{product.display_name} {lot.name or ''}: "
            f"{scanned.get((product, lot), 0):g} / {quantity:g}"
            for (product, lot), quantity in self._trip_on_board_by_lot().items()
        )

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    is_subcontract_stock_barcode = fields.Boolean(
        compute="_compute_is_subcontract_stock_barcode"
    )

    @api.depends("move_id.is_subcontract")
    def _compute_is_subcontract_stock_barcode(self) -> None:
        self.is_subcontract_stock_barcode = False
        for move_line in self:
            # Hide if not encoding state or it is not a subcontracting picking
            if (
                move_line.state in ("draft", "cancel", "done")
                or not move_line.move_id.is_subcontract
            ):
                continue
            move_line.is_subcontract_stock_barcode = True

    @api.depends("is_subcontract_stock_barcode")
    def _compute_hide_lot_name(self) -> None:
        super()._compute_hide_lot_name()
        for line in self:
            if line.is_subcontract_stock_barcode and line.tracking in ("lot", "serial"):
                line.hide_lot = False
                line.hide_lot_name = True

    @api.model_create_multi
    def create(self, vals_list):
        """In the case of a subcontract move, a move line may be created without an initial
        `move_id`- thus the line will use whatever source location value is defined on the picking,
        which is less precise than using a value defined on a move that may take ownership of the
        MoveLine after its initial creation.
        """
        move_lines = super().create(vals_list)
        subcontract_moves = move_lines.move_id.filtered("is_subcontract")
        _debug.lifecycle(
            "create", lines=move_lines, subcontract_moves=len(subcontract_moves)
        )
        for move in subcontract_moves:
            subcontract_move_lines = move.move_line_ids & move_lines
            if subcontract_move_lines.location_id != move.location_id:
                _debug.logic(
                    "subcontract_line_relocated",
                    move=move.id,
                    lines=len(subcontract_move_lines),
                    location=move.location_id.id,
                )
                subcontract_move_lines.location_id = move.location_id
        return move_lines

    def write(self, vals):
        """Make sure to use trace_ids instead of lot_names in case of subcontracting moves."""
        if "lot_name" in vals and any(l.move_id.is_subcontract for l in self):
            trace_id = self.env["product.trace"].search(
                [
                    ("product_id", "=", self.product_id),
                    "|",
                    ("company_id", "=", self.company_id),
                    ("company_id", "=", False),
                    ("name", "=", vals["lot_name"]),
                ]
            )
            _debug.logic(
                "subcontract_lot_name_resolved",
                lines=self,
                by="existing" if trace_id else "created",
            )
            if not trace_id:
                trace_id = self.env["product.trace"].create(
                    {"product_id": self.product_id.id, "name": vals["lot_name"]}
                )
            vals["lot_name"] = False
            vals["trace_id"] = trace_id.id
        return super().write(vals)

    def _get_fields_stock_barcode(self):
        """Inject info if the line is subcontract and have tracked component"""
        return super()._get_fields_stock_barcode() + ["is_subcontract_stock_barcode"]

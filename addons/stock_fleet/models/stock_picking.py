from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    dispatch_management = fields.Boolean(
        tracking=True,
        help="Enable this option to display dispatch management related details in the batch/wave form view and operations kanban overview.",
    )
    dock_ids = fields.Many2many(
        comodel_name="stock.location",
        relation="dock_location_stock_picking_type_rel",
        compute="_compute_dock_ids",
        store=True,
        readonly=False,
        domain="[('warehouse_id', '=', warehouse_id), ('usage', '=', 'internal')]",
        tracking=True,
    )

    @api.depends("warehouse_id")
    def _compute_dock_ids(self) -> None:
        for picking_type in self:
            if (
                picking_type.warehouse_id != picking_type._origin.warehouse_id
                and picking_type.dock_ids
            ):
                picking_type.dock_ids = [Command.clear()]


class StockPicking(models.Model):
    _inherit = "stock.picking"

    zip = fields.Char(
        related="partner_id.zip",
        string="Zip",
        search="_search_zip",
    )

    def _search_zip(self, operator, value) -> list:
        return [("partner_id.zip", operator, value)]

    def write(self, vals):
        _debug.lifecycle("fleet_picking_write", pickings=self, fields=len(vals))
        docked = (
            self.filtered(lambda picking: picking.batch_id.dock_id)
            if "batch_id" in vals
            else self.browse()
        )
        res = super().write(vals)
        if "batch_id" not in vals:
            return res
        batch = self.env["stock.picking.batch"].browse(vals.get("batch_id"))
        if batch and batch.dock_id:
            batch._set_moves_destination_to_dock()
        elif docked:
            docked._reset_location()
        return res

    def _get_moves_outside_destination(self):
        self.check_singleton()
        return self.move_ids.filtered(
            lambda move: (
                not move.location_dest_id._is_descendant_of(self.location_dest_id)
            )
        )

    def _get_moves_outside_source(self):
        self.check_singleton()
        return self.move_ids.filtered(
            lambda move: (
                move.state not in ("done", "cancel")
                and not move.location_id._is_descendant_of(self.location_id)
            )
        )

    def _reset_location(self) -> None:
        _debug.logic("fleet_picking_location_reset", pickings=self)
        for picking in self:
            moves = picking._get_moves_outside_destination()
            moves.write({"location_dest_id": picking.location_dest_id.id})
            resourced = picking._get_moves_outside_source()
            if resourced:
                _debug.logic(
                    "fleet_picking_source_restored", picking=picking, moves=resourced
                )
                resourced.write({"location_id": picking.location_id.id})

from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from .stock_picking_trip import MERGE_TRIPS

_debug = DebugLog(__name__)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    vehicle_id = fields.Many2one(comodel_name="resource.asset.vehicle")
    vehicle_model_id = fields.Many2one(
        comodel_name="product.product",
        compute="_compute_vehicle_model_id",
        store=True,
        readonly=False,
        domain="[('asset_kind_id.code', '=', 'vehicle')]",
    )
    allowed_dock_ids = fields.Many2many(
        related="picking_type_id.dock_ids",
        string="Allowed Docks",
    )
    dock_id = fields.Many2one(
        comodel_name="stock.location",
        compute="_compute_dock_id",
        store=True,
        readonly=False,
        domain="[('id', 'child_of', allowed_dock_ids)]",
    )
    vehicle_weight_capacity = fields.Float(
        related="vehicle_model_id.weight_capacity",
        string="Vehcilce Payload Capacity",
    )
    weight_uom_name = fields.Char(
        string="Weight unit of measure label",
        compute="_compute_weight_uom_name",
    )
    vehicle_volume_capacity = fields.Float(
        related="vehicle_model_id.volume_capacity",
        string="Max Volume (m³)",
    )
    volume_uom_name = fields.Char(
        string="Volume unit of measure label",
        compute="_compute_volume_uom_name",
    )
    driver_id = fields.Many2one(
        comodel_name="res.partner",
        compute="_compute_driver_id",
        store=True,
        readonly=False,
    )
    trip_shipping_weight = fields.Float(
        string="Shipping Weight",
        digits="Stock Weight",
        compute="_compute_capacity_percentage",
        help="What the transfers put on the vehicle: their shipping weight, the "
        "tare of their packages included, or the weight of their demand while "
        "nothing is reserved.",
    )
    used_weight_percentage = fields.Float(
        string="Weight %",
        compute="_compute_capacity_percentage",
    )
    used_volume_percentage = fields.Float(
        string="Volume %",
        compute="_compute_capacity_percentage",
    )
    end_date = fields.Datetime(
        compute="_compute_end_date",
        store=True,
    )
    has_dispatch_management = fields.Boolean(
        related="picking_type_id.dispatch_management",
        string="Dispatch Management",
    )

    @api.depends("date_planned")
    def _compute_end_date(self) -> None:
        for batch in self:
            if not batch.end_date or (
                batch.date_planned and batch.end_date < batch.date_planned
            ):
                batch.end_date = (
                    batch.date_planned + timedelta(hours=1)
                    if batch.date_planned
                    else False
                )

    @api.depends("vehicle_id")
    def _compute_vehicle_model_id(self) -> None:
        for rec in self:
            if rec.vehicle_id:
                rec.vehicle_model_id = rec.vehicle_id.product_id

    @api.depends(
        "picking_ids",
        "picking_ids.location_id",
        "picking_ids.location_dest_id",
        "picking_type_id",
    )
    def _compute_dock_id(self) -> None:
        for batch in self:
            if batch.picking_type_id != batch._origin.picking_type_id and batch.dock_id:
                batch.dock_id = False
            if (
                batch.picking_ids
                and len(batch.picking_ids.location_id) == 1
                and batch.picking_ids.location_id in batch.allowed_dock_ids
            ):
                batch.dock_id = batch.picking_ids.location_id

    def _compute_weight_uom_name(self) -> None:
        self.weight_uom_name = (
            self.env["product.template"]._get_uom_from_setting("weight").display_name
        )

    def _compute_volume_uom_name(self) -> None:
        self.volume_uom_name = (
            self.env["product.template"]._get_uom_from_setting("volume").display_name
        )

    @api.depends("vehicle_id")
    def _compute_driver_id(self) -> None:
        for rec in self:
            rec.driver_id = rec.vehicle_id.operator_id.partner_id

    @api.depends(
        "picking_ids.state",
        "estimated_shipping_weight",
        "picking_ids.move_line_ids",
        "picking_ids.move_ids.state",
        "picking_ids.move_ids.product_qty",
        "picking_ids.move_ids.product_id.weight",
        "vehicle_model_id.weight_capacity",
        "estimated_shipping_volume",
        "vehicle_model_id.volume_capacity",
    )
    def _compute_capacity_percentage(self) -> None:
        _debug.perf.count("batch_capacity_compute", batches=self)
        self.used_weight_percentage = False
        self.used_volume_percentage = False
        for batch in self:
            batch.trip_shipping_weight = batch.estimated_shipping_weight + sum(
                picking.move_ids.filtered(
                    lambda move: move.state != "cancel"
                )._trip_goods_weight()
                for picking in batch.picking_ids
                if picking.state != "cancel" and not picking.move_line_ids
            )
            if batch.vehicle_weight_capacity:
                batch.used_weight_percentage = 100 * (
                    batch.trip_shipping_weight / batch.vehicle_weight_capacity
                )
            if batch.vehicle_volume_capacity:
                batch.used_volume_percentage = 100 * (
                    batch.estimated_shipping_volume / batch.vehicle_volume_capacity
                )

    @api.model_create_multi
    def create(self, vals_list):
        _debug.lifecycle("fleet_batch_create", count=len(vals_list))
        batches = super().create(vals_list)
        batches.order_on_zip()
        batches.filtered(lambda b: b.dock_id)._set_moves_destination_to_dock()
        return batches

    def write(self, vals):
        _debug.lifecycle("fleet_batch_write", batches=self, fields=len(vals))
        res = super().write(vals)
        if "picking_ids" in vals:
            self.order_on_zip()
        if "dock_id" in vals:
            self._set_moves_destination_to_dock()
        return res

    def order_on_zip(self) -> None:
        _debug.pipeline("batch_order_on_zip", batches=self)
        sorted_records = self.picking_ids.sorted(lambda p: p.zip or "")
        for idx, record in enumerate(sorted_records, start=1):
            record.batch_sequence = idx

    def _set_moves_destination_to_dock(self) -> None:
        _debug.pipeline("batch_moves_to_dock", batches=self)
        for batch in self:
            if not batch.dock_id:
                batch.picking_ids._reset_location()
            elif batch.picking_type_id.code in ["internal", "incoming"]:
                batch.picking_ids.move_ids.write({"location_dest_id": batch.dock_id.id})
            else:
                batch._load_moves_from_dock()

    def _load_moves_from_dock(self) -> None:
        self.check_singleton()
        dock = self.dock_id
        moves = self.picking_ids.move_ids.filtered(
            lambda move: (
                move.state not in ("done", "cancel") and move.location_id != dock
            )
        )
        fed_elsewhere = moves.filtered(
            lambda move: any(
                not origin.location_dest_id._is_descendant_of(dock)
                for origin in move.move_orig_ids
                if origin.state != "cancel"
            )
        )
        if fed_elsewhere:
            _debug.logic(
                "batch_dock_keeps_fed_moves", batch=self, dock=dock, moves=fed_elsewhere
            )
        loaded = moves - fed_elsewhere
        if loaded:
            _debug.logic(
                "batch_dock_sources_moves", batch=self, dock=dock, moves=loaded
            )
            loaded.write({"location_id": dock.id})

    def action_merge(self):
        return super(
            StockPickingBatch, self.with_context(**{MERGE_TRIPS: True})
        ).action_merge()

    def _get_domain_allowed_picking(self):
        domain = super()._get_domain_allowed_picking()
        if self.picking_type_id.dispatch_batch_required:
            domain &= Domain("batch_id", "=", False) | Domain(
                "batch_id", "in", self._origin.ids
            )
        return domain

    def _prepare_merged_batch_vals(self):
        self.check_singleton()
        vals = super()._prepare_merged_batch_vals()
        vals.update(
            {
                "vehicle_id": self.vehicle_id.id,
                "dock_id": self.dock_id.id,
            }
        )
        return vals

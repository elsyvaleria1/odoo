from odoo import api, fields, models

from odoo.addons.maintenance.models.maintenance_order import OPEN_STATES


class ProductTrace(models.Model):
    _inherit = "product.trace"

    is_deployed = fields.Boolean(
        compute="_compute_asset_operational_state",
        store=True,
        help="Asset is in a deployed location (operationally in use)",
    )
    is_in_maintenance = fields.Boolean(
        compute="_compute_asset_operational_state",
        store=True,
        help="Asset is in a maintenance location",
    )
    is_in_storage = fields.Boolean(
        compute="_compute_asset_operational_state",
        store=True,
        help="Asset is in storage (not deployed, not in maintenance)",
    )

    maintenance_state = fields.Selection(
        selection=[
            ("none", "None"),
            ("good", "Good"),
            ("warning", "Warning"),
            ("critical", "Critical"),
            ("obsolete", "Obsolete"),
        ],
        compute="_compute_maintenance_state",
        store=True,
        readonly=True,
    )
    maintenance_ok = fields.Boolean(
        related="product_id.maintenance_ok",
        string="Maintenance Enabled",
        readonly=True,
    )

    @api.depends(
        "location_id",
        "location_id.deployed_location",
        "location_id.maintenance_location",
    )
    def _compute_asset_operational_state(self) -> None:
        for lot in self:
            lot.is_deployed = lot.location_id.deployed_location
            lot.is_in_maintenance = lot.location_id.maintenance_location
            lot.is_in_storage = not (lot.is_deployed or lot.is_in_maintenance)

    @api.depends(
        "maintenance_ok",
        "active",
        "asset_id.maintenance_ids.maintenance_type",
        "asset_id.maintenance_ids.state",
        "asset_id.maintenance_ids.date_scheduled_start",
    )
    def _compute_maintenance_state(self) -> None:
        for lot in self:
            if not lot.maintenance_ok:
                lot.maintenance_state = "none"
            elif not lot.active:
                lot.maintenance_state = "obsolete"
            else:
                lot.maintenance_state = lot._get_open_maintenance_state() or "good"

    def _get_open_maintenance_state(self) -> str | None:
        self.check_singleton()
        now = fields.Datetime.now()
        open_types = {
            order.maintenance_type
            for order in self.asset_id.maintenance_ids
            if order.state in OPEN_STATES
            and (
                order.maintenance_type == "corrective"
                or order.state == "in_progress"
                or (order.date_scheduled_start and order.date_scheduled_start <= now)
            )
        }
        if "corrective" in open_types:
            return "critical"
        if "preventive" in open_types:
            return "warning"
        return None

    def action_view_maintenance_orders(self):
        self.check_singleton()
        return self.asset_id.action_view_maintenance()

    def action_create_maintenance_order(self):
        self.check_singleton()
        return self.asset_id.action_create_maintenance_order()

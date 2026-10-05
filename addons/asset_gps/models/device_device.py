from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DeviceDevice(models.Model):
    _inherit = "device.device"

    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Assigned Asset",
        compute="_compute_tracked_asset_id",
        inverse="_inverse_tracked_asset_id",
        search="_search_tracked_asset_id",
        context={"active_test": False},
        help="Asset represented by the tracked resource, archived or not",
    )

    @api.depends("tracked_resource_id", "tracked_resource_id.kind_id")
    def _compute_tracked_asset_id(self):
        for device in self:
            tracked = device.tracked_resource_id
            device.asset_id = tracked if tracked.kind_id else False

    def _inverse_tracked_asset_id(self):
        with self.env.cr.savepoint():
            for device in self:
                target = device.asset_id
                previous = device.tracked_resource_id
                # clearing an empty asset projection leaves a tracked resource
                # that is not a thing alone
                if previous and previous != target and (previous.kind_id or target):
                    previous.gps_device_id = False
                if target:
                    target.gps_device_id = device

    def _search_tracked_asset_id(self, operator, value):
        if operator not in ("in", "not in", "any", "not any"):
            return NotImplemented
        if operator in ("in", "not in"):
            ids = [v for v in value if v]
            domain = Domain("tracked_resource_id", "in", ids) & Domain(
                "tracked_resource_id.kind_id", "!=", False
            )
            if len(ids) < len(value):
                domain |= Domain("tracked_resource_id.kind_id", "=", False)
        else:
            domain = Domain("tracked_resource_id", "any", value) & Domain(
                "tracked_resource_id.kind_id", "!=", False
            )
        return ~domain if operator.startswith("not") else domain

    def action_view_tracked_asset(self) -> dict | None:
        # Not action_view_own_asset: asset_device names that for the asset a
        # device IS -- a phone, an access terminal -- and it auto-installs beside
        # us, so taking its name would shadow it. This one is the asset a device
        # reports FOR.
        self.check_singleton()
        if not self.asset_id:
            _debug.logic("tracked_asset.none", device=self)
            return None
        return self.asset_id.get_formview_action()

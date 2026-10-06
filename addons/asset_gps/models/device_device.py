from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DeviceDevice(models.Model):
    _inherit = "device.device"

    asset_id = fields.Many2one(
        comodel_name="resource.asset",
        string="Assigned Asset",
        compute="_compute_tracked_asset_id",
        inverse="_inverse_tracked_asset_id",
        search="_search_tracked_asset_id",
        context={"active_test": False},
        help="Asset represented by the tracked resource, archived or not",
    )

    @api.depends("tracked_resource_id", "tracked_resource_id.asset_id")
    def _compute_tracked_asset_id(self):
        for device in self:
            device.asset_id = device.tracked_resource_id.asset_id

    def _inverse_tracked_asset_id(self):
        # The adapter follows asset permissions, as the old asset-side inverse
        # did. Granting broad resource writes to an asset editor is unnecessary.
        with self.env.cr.savepoint():
            for device in self:
                target = device.asset_id
                previous = device.tracked_resource_id
                previous_asset = previous.asset_id
                if previous and previous != target.resource_id:
                    if previous_asset:
                        previous_asset.gps_device_id = False
                    elif target:
                        # Moving away from a non-asset target requires that
                        # target's resource authority; clearing an empty asset
                        # projection must leave the non-asset target alone.
                        previous.gps_device_id = False
                if target:
                    target.gps_device_id = device

    def _search_tracked_asset_id(self, operator, value):
        return [("tracked_resource_id.asset_id", operator, value)]

    def action_view_tracked_asset(self) -> dict | None:
        # Not action_view_own_asset: asset_device names that for the asset a
        # device IS -- a phone, an access terminal -- and it auto-installs beside
        # us, so taking its name would shadow it. This one is the asset a device
        # reports FOR.
        self.check_singleton()
        if not self.asset_id:
            _debug.logic("tracked_asset.none", device=self)
            return None
        return {
            "name": self.asset_id.display_name,
            "type": "ir.actions.act_window",
            "res_model": "resource.asset",
            "res_id": self.asset_id.id,
            "view_mode": "form",
            "target": "current",
        }

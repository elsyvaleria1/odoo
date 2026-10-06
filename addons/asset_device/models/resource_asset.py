from odoo import fields, models


class ResourceAsset(models.Model):
    _inherit = "resource.asset"

    device_ids = fields.One2many(
        comodel_name="device.device",
        inverse_name="own_asset_id",
        string="Devices",
        help="Remote devices that are this asset.",
    )
    count_device_devices = fields.Count(
        count_of="device_ids",
        compute_sudo=True,
    )

    def action_view_device_devices(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Devices"),
            "res_model": "device.device",
            "view_mode": "list,form",
            "domain": [("own_asset_id", "=", self.id)],
            "context": {"default_own_asset_id": self.id},
        }

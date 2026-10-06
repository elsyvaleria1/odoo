from odoo import api, fields, models
from odoo.fields import Domain


class IotDevice(models.Model):
    _name = "iot.device"
    _inherit = ["iot.device", "mixin.pos.load"]

    associated_pos_config_ids = fields.Many2many(
        comodel_name="pos.config",
        string="Associated PoS",
        compute="_compute_associated_pos_config_ids",
    )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("id", "in", config.iot_device_ids.ids)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["iot_ip", "iot_id", "identifier", "type", "manual_measurement"]

    @api.depends("type")
    def _compute_associated_pos_config_ids(self) -> None:
        """Compute the associated PoS config ids for the Current device"""
        pos_config = self.env["pos.config"]
        field_map = {
            "scanner": ("iface_scanner_ids", "in"),
            "printer": ("iface_printer_id", "="),
            "display": ("iface_display_id", "="),
            "scale": ("iface_scale_id", "="),
            "fiscal_data_module": ("iface_fiscal_data_module", "=")
            if "iface_fiscal_data_module" in pos_config._fields
            else (None, None),
        }

        for device in self:
            field, operator = field_map.get(device.type, (None, None))

            if not field:
                device.associated_pos_config_ids = pos_config
                continue

            domain = Domain(
                ["&", ("is_posbox", "=", True), (field, operator, device.id)]
            )
            device.associated_pos_config_ids = pos_config.search(domain)

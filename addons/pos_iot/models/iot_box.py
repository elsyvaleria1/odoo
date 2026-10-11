from odoo import api, fields, models
from odoo.fields import Domain


class IotBox(models.Model):
    _name = "iot.box"
    _inherit = ["iot.box", "mixin.pos.load"]

    associated_pos_config_ids = fields.Many2many(
        comodel_name="pos.config",
        string="Associated PoS",
        compute="_compute_associated_pos_config_ids",
    )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [
            (
                "id",
                "in",
                [device["iot_id"] for device in data["iot.device"] if device["iot_id"]],
            )
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["ip", "name", "identifier", "version"]

    @api.depends("device_ids")
    def _compute_associated_pos_config_ids(self) -> None:
        for box in self:
            domain = Domain("is_posbox", "=", True) & Domain.OR(
                Domain(field_name, "in", box.device_ids.ids)
                for field_name in (
                    "iface_printer_id",
                    "iface_display_id",
                    "iface_scale_id",
                    "iface_scanner_ids",
                )
            )
            box.associated_pos_config_ids = self.env["pos.config"].search(domain)

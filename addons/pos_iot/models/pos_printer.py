from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PosPrinter(models.Model):
    _inherit = "pos.printer"

    device_id = fields.Many2one(
        comodel_name="iot.device",
        string="IoT Device",
        domain="['&', ('type', '=', 'printer'), ('subtype', '=', 'receipt_printer'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    device_identifier = fields.Char(related="device_id.identifier")
    proxy_ip = fields.Char(
        related="device_id.iot_ip",
        size=45,
        store=True,
    )

    @api.constrains("proxy_ip")
    def _check_proxy_ip(self) -> None:
        for record in self:
            if (
                record.printer_type == "iot"
                and record.device_id
                and not record.proxy_ip
            ):
                raise ValidationError(self.env._("Proxy IP cannot be empty."))

    @api.model
    def _load_pos_data_fields(self, config):
        result = super()._load_pos_data_fields(config)
        result += ["device_identifier", "device_id"]
        return result

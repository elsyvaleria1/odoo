from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_whatsapp_enabled = fields.Boolean(
        related="pos_config_id.whatsapp_enabled",
        readonly=False,
    )
    pos_receipt_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        related="pos_config_id.receipt_template_id",
        readonly=False,
    )
    pos_invoice_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        related="pos_config_id.invoice_template_id",
        readonly=False,
    )

    @api.constrains("pos_receipt_template_id")
    def _check_whatsapp_receipt_template(self) -> None:
        for record in self:
            if record.pos_receipt_template_id:
                if not record.pos_receipt_template_id.header_type == "image":
                    raise ValidationError(
                        self.env._(
                            "Receipt Whatsapp template should have Image Header Type"
                        )
                    )
                if not record.pos_receipt_template_id.phone_field:
                    raise ValidationError(
                        self.env._(
                            "Receipt Whatsapp template should have a phone field"
                        )
                    )

    @api.constrains("pos_invoice_template_id")
    def _check_whatsapp_invoice_template(self) -> None:
        for record in self:
            if (
                record.pos_invoice_template_id
                and not record.pos_receipt_template_id.phone_field
            ):
                raise ValidationError(
                    self.env._("Invoice Whatsapp template should have a phone field")
                )

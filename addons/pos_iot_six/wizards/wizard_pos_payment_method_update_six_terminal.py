from odoo import api, fields, models


class WizardPosPaymentMethodUpdateSixTerminal(models.TransientModel):
    _name = "wizard.pos.payment.method.update.six.terminal"
    _description = "Connect a Six Payment Terminal"

    iot_box_id = fields.Many2one(
        comodel_name="iot.box",
        string="IoT Box",
        default=lambda self: self._get_existing_iot_box_id(),
        required=True,
        help="The IoT Box that your Six terminal is connected to.",
    )
    iot_box_ip = fields.Char(related="iot_box_id.ip")
    six_terminal_id = fields.Char(
        related="iot_box_id.six_terminal_id",
        readonly=False,
    )
    terminal_device_id = fields.Many2one(
        comodel_name="iot.device",
        default=lambda self: self._get_existing_terminal_device_id(),
        required=True,
    )

    def _get_existing_terminal_device_id(self):
        payment_method = self.env["pos.payment.method"].browse(
            self.env.context["active_id"]
        )
        return payment_method.iot_device_id

    def _get_existing_iot_box_id(self):
        payment_method = self.env["pos.payment.method"].browse(
            self.env.context["active_id"]
        )
        return payment_method.iot_device_id.iot_id

    @api.onchange("iot_box_id")
    def _on_change_iot_box_id(self) -> None:
        if (
            self.terminal_device_id
            and self.terminal_device_id.iot_id != self.iot_box_id
        ):
            self.terminal_device_id = None

    def action_add_payment_method(self) -> None:
        self.check_singleton()
        payment_method = self.env["pos.payment.method"].browse(
            self.env.context["active_id"]
        )
        payment_method.iot_device_id = self.terminal_device_id

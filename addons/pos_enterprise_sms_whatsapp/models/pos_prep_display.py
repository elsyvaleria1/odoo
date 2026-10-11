import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PosPrepDisplay(models.Model):
    _inherit = "pos.prep.display"

    sms_enabled = fields.Boolean(
        string="SMS Enabled",
        default=False,
    )
    sms_order_received_id = fields.Many2one(
        comodel_name="sms.template",
        string="Order received (SMS)",
        default=lambda self: self._get_default_sms_template("received"),
    )
    sms_order_ready_id = fields.Many2one(
        comodel_name="sms.template",
        string="Order is ready (SMS)",
        default=lambda self: self._get_default_sms_template("ready"),
    )

    whatsapp_enabled = fields.Boolean(
        string="WhatsApp Enabled",
        default=False,
    )
    whatsapp_order_received_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Order received (wa)",
        default=lambda self: self._get_default_whatsapp_template("received"),
    )
    whatsapp_order_ready_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Order is ready (wa)",
        default=lambda self: self._get_default_whatsapp_template("ready"),
    )

    def send_order_notifications(self, order, event_type) -> None:
        self.check_singleton()
        if not order.exists():
            return

        partner = order.partner_id
        if not partner:
            _logger.info("Order %s has no partner, skipping", order.id)
            return

        if self.sms_enabled:
            sms_template = (
                self.sms_order_received_id
                if event_type == "received"
                else self.sms_order_ready_id
            )
            if sms_template:
                composer = self.env["wizard.sms.sms.send"].create(
                    {
                        "composition_mode": "comment",
                        "template_id": sms_template.id,
                        "res_model": "pos.order",
                        "res_ids": order.id,
                    }
                )
                composer.action_send_sms()

        if self.whatsapp_enabled:
            whatsapp_template = (
                self.whatsapp_order_received_id
                if event_type == "received"
                else self.whatsapp_order_ready_id
            )
            if whatsapp_template:
                composer = self.env["wizard.whatsapp.message.send"].create(
                    {
                        "phone": order.partner_id.phone_ids._primary().number,
                        "res_model": "pos.order",
                        "res_ids": order.id,
                        "wa_template_id": whatsapp_template.id,
                    }
                )
                composer._send_whatsapp_template()

    def _get_default_sms_template(self, event_type):
        if event_type == "received":
            return self.env.ref(
                "pos_enterprise_sms_whatsapp.sms_template_order_received_confirmation_pos",
                raise_if_not_found=False,
            )
        elif event_type == "ready":
            return self.env.ref(
                "pos_enterprise_sms_whatsapp.sms_template_order_ready_pos",
                raise_if_not_found=False,
            )
        return None

    def _get_default_whatsapp_template(self, event_type):
        if event_type == "received":
            return self.env.ref(
                "pos_enterprise_sms_whatsapp.whatsapp_order_received_confirmation_pos",
                raise_if_not_found=False,
            )
        elif event_type == "ready":
            return self.env.ref(
                "pos_enterprise_sms_whatsapp.whatsapp_order_ready_confirmation_pos",
                raise_if_not_found=False,
            )
        return None

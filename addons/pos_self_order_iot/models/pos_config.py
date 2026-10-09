import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = "pos.config"

    self_ordering_iot_available_iot_box_ids = fields.One2many(
        comodel_name="iot.box",
        inverse_name="pos_id",
        string="Available IoT Boxes",
        required=True,
        domain="[('can_be_kiosk', '=', True)]",
    )

    def _load_self_data_models(self):
        models = super()._load_self_data_models()
        models += ["iot.device", "iot.box"]
        return models

    def action_view_wizard(self):
        """Override the ir.action.act_url to open the kiosk on the selected IoT Boxes (if any)."""
        url_in_new_tab_action = super().action_view_wizard()  # Configure pos session

        # If no IoT Box is selected in the settings, open the kiosk in a new tab
        if not self.self_ordering_iot_available_iot_box_ids:
            return url_in_new_tab_action

        display_identifiers = [
            d.identifier
            for box in self.self_ordering_iot_available_iot_box_ids
            for d in box.device_ids
            if d.type == "display"
        ]

        self.env["iot.channel"]._send_message(
            {
                "iot_identifiers": [
                    iot_box.identifier
                    for iot_box in self.self_ordering_iot_available_iot_box_ids
                ],
                "device_identifiers": display_identifiers,
                "action": "open_kiosk",
                "pos_id": self.id,
                "access_token": self.self_ordering_access_token,
            }
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "info",
                "message": self.env._(
                    "Opening the kiosk on %s",
                    ", ".join(
                        self.self_ordering_iot_available_iot_box_ids.mapped("name")
                    ),
                ),
            },
        }

    def has_valid_self_payment_method(self) -> bool:
        res = super().has_valid_self_payment_method()
        if self.self_ordering_mode == "mobile":
            return bool(res)
        return bool(res or any(pm.iot_device_id for pm in self.payment_method_ids))

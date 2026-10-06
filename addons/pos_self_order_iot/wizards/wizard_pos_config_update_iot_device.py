from odoo import Command, models


class WizardPosConfigUpdateIotDevice(models.TransientModel):
    _inherit = "wizard.pos.config.update.iot.device"

    def action_autoconfigure(self) -> dict | None:
        if not self.iot_box_id:
            return None

        for pos_config in self.pos_config_ids:
            if (
                pos_config.self_ordering_mode == "kiosk"
                and self.iot_box_id.can_be_kiosk
            ):
                pos_config.self_ordering_iot_available_iot_box_ids = [
                    Command.link(self.iot_box_id.id)
                ]

        return super().action_autoconfigure()

from odoo import models


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _get_bus_channels(self, channels):
        channels = super()._get_bus_channels(channels)
        group = self.env.ref("device.group_device_user", raise_if_not_found=False)
        # beside the group's own channel, which bus subscribes to through
        # all_group_ids: one channel of that group per company of the user
        if not group or group not in self.env.user.all_group_ids:
            return channels
        return [*channels, *((group, cid) for cid in self.env.user.company_ids.ids)]

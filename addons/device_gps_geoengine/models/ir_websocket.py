from odoo import models


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _implicit_bus_channels(self):
        channels = super()._implicit_bus_channels()
        group = self.env.ref("device.group_device_user", raise_if_not_found=False)
        if not group or group not in self.env.user.all_group_ids:
            return channels
        return [*channels, *((group, cid) for cid in self.env.user.company_ids.ids)]

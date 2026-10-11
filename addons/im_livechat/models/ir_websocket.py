from odoo import models


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _bus_channels_by_name(self, names):
        result = super()._bus_channels_by_name(names)
        name = "im_livechat.looking_for_help"
        if name in result and self.env.user.has_group(
            "im_livechat.im_livechat_group_user"
        ):
            result[name] = [
                (self.env.ref("im_livechat.im_livechat_group_user"), "LOOKING_FOR_HELP")
            ]
        return result

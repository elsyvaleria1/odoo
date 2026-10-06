from odoo.addons.ai.controllers.main import AIController


class AICrmLivechatController(AIController):
    def _is_unlink_on_close_required(self, channel) -> bool:
        # allow to check discussions from the leads created by agents in livechats
        if channel.channel_type == "livechat" and channel.has_crm_lead:
            return False
        return super()._is_unlink_on_close_required(channel)

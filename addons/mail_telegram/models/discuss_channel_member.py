from odoo import models


class DiscussChannelMember(models.Model):
    _inherit = "discuss.channel.member"

    def _notify_typing(self, is_typing) -> None:
        super()._notify_typing(is_typing)
        if not is_typing:
            return
        mirrors = self.env["telegram.mirror"]
        for member in self:
            if not member.partner_id.user_ids.filtered(lambda u: not u.share):
                continue
            for mirror in mirrors._of_thread(member.channel_id):
                mirror._show_typing()

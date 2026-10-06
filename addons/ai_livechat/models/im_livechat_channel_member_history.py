from odoo import fields, models


class ImLivechatChannelMemberHistory(models.Model):
    _inherit = "im_livechat.channel.member.history"

    ai_agent_id = fields.Many2one(
        comodel_name="ai.agent",
        compute="_compute_member_fields",
        store=True,
        index="btree_not_null",
    )

    def _compute_member_fields(self) -> None:
        super()._compute_member_fields()
        for history in self:
            history.ai_agent_id = history.ai_agent_id or history.member_id.ai_agent_id

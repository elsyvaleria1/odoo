from odoo import api, fields, models


class WizardKnowledgeArticleInviteMember(models.TransientModel):
    _name = "wizard.knowledge.article.invite.member"
    _description = "Knowledge Invite Wizard"

    article_id = fields.Many2one(
        comodel_name="knowledge.article",
        required=True,
        ondelete="cascade",
    )
    have_share_partners = fields.Boolean(compute="_compute_have_share_partners")
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Recipients",
        required=True,
    )
    permission = fields.Selection(
        selection=[("write", "Can edit"), ("read", "Can read"), ("none", "No access")],
        default="write",
        required=True,
    )
    message = fields.Html()

    def action_invite_members(self):
        self.article_id.invite_members(self.partner_ids, self.permission, self.message)

    @api.depends("partner_ids")
    def _compute_have_share_partners(self) -> None:
        for wizard in self:
            wizard.have_share_partners = any(
                partner_id.partner_share for partner_id in self.partner_ids
            )

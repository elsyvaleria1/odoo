from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    agent_ids = fields.One2many(
        comodel_name="ai.agent",
        inverse_name="partner_id",
    )

    def _compute_presence(self) -> None:
        agent_partners = self.with_context(active_test=False).filtered(
            lambda record: record.agent_ids
        )
        agent_partners.im_status = "agent"
        agent_partners.offline_since = False
        super(ResPartner, self - agent_partners)._compute_presence()

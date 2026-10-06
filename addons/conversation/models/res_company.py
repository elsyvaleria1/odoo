from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    conversation_config_id = fields.Many2one(
        comodel_name="conversation.config",
        compute="_compute_conversation_config_id",
        search="_search_conversation_config_id",
    )

    def _search_conversation_config_id(self, operator, value):
        return self._search_config_link("conversation.config", operator, value)

    def _compute_conversation_config_id(self) -> None:
        self._compute_config_link("conversation_config_id")

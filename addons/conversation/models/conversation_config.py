from odoo import api, fields, models


class ConversationConfig(models.Model):
    _name = "conversation.config"
    _description = "A company's conversation configuration"
    _inherit = ["mixin.company.config"]

    analysis_context = fields.Text(
        help="Who the company is, for the analyst: its trade, its brands, its region",
    )

    @api.model
    def action_open_configs(self) -> dict:
        configs = self._for_each(self.env.companies)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Analysis context"),
            "res_model": self._name,
            "view_mode": "list",
            "domain": [("id", "in", configs.ids)],
        }

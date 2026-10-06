from odoo import api, fields, models


class WalletCard(models.Model):
    _inherit = "wallet.card"

    reorder_rule_ids = fields.One2many(
        comodel_name="wallet.reorder.rule",
        inverse_name="card_id",
        string="Reordering Rules",
    )
    reorder_rule_id = fields.Many2one(
        comodel_name="wallet.reorder.rule",
        compute="_compute_reorder_rule_id",
        store=True,
        help="The card's reordering rule, one at most.",
    )
    amount_to_reload = fields.Monetary(related="reorder_rule_id.amount_to_reload")

    @api.depends("reorder_rule_ids")
    def _compute_reorder_rule_id(self) -> None:
        for card in self:
            card.reorder_rule_id = card.reorder_rule_ids[:1]

    def action_view_reorder_rule(self) -> dict:
        self.check_singleton()
        rule = self.reorder_rule_id
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Reordering Rule"),
            "res_model": "wallet.reorder.rule",
            "view_mode": "form",
            "res_id": rule.id,
            "context": {"default_card_id": self.id},
        }

from odoo import fields, models


class WalletAccount(models.Model):
    _inherit = "wallet.account"

    reload_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Top-up Product",
        default=lambda self: self._default_reload_product(),
        check_company=True,
        help="The product a reload of this wallet is purchased as.",
    )
    reorder_rule_ids = fields.One2many(
        comodel_name="wallet.reorder.rule",
        inverse_name="account_id",
    )
    count_reorder_rule = fields.Count(count_of="reorder_rule_ids")

    def _default_reload_product(self):
        return self.env.ref(
            "wallet_reorder.product_wallet_reload", raise_if_not_found=False
        )

    def action_view_reorder_rules(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Reordering Rules"),
            "res_model": "wallet.reorder.rule",
            "view_mode": "list,form",
            "domain": [("account_id", "=", self.id)],
            "context": {"default_account_id": self.id},
        }

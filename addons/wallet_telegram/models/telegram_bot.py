from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TelegramBot(models.Model):

    _inherit = "telegram.bot"

    wallet_account_ids = fields.Many2many(
        comodel_name="wallet.account",
        string="Wallet Accounts",
        domain="[('company_id', 'in', company_ids)]",
        help="Accounts available through /saldo and /recarga. Each person sees "
        "only cards assigned to their own contact as holder.",
    )

    @api.constrains("wallet_account_ids", "company_ids")
    def _check_wallet_companies(self) -> None:
        for bot in self:
            if bot.wallet_account_ids.company_id - bot.company_ids:
                raise ValidationError(
                    self.env._(
                        "Wallet accounts must belong to companies this bot serves."
                    )
                )

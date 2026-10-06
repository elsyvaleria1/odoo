from odoo import api, fields, models


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    payment_approval_category_id = fields.Many2one(
        comodel_name="approval.category",
        check_company=True,
        help="Category to be used for payment approval requests created from Telegram.",
    )
    especie_approval_category_id = fields.Many2one(
        comodel_name="approval.category",
        check_company=True,
        help="Category for payment-in-kind approval requests created from Telegram.",
    )
    has_pago_command = fields.Boolean(
        compute="_compute_has_payment_command",
        store=True,
        help="Technical field to check if the /pago command is enabled for this bot.",
    )
    has_especie_command = fields.Boolean(
        compute="_compute_has_payment_command",
        store=True,
        help="Technical field to check if the /especie command is enabled for this bot.",
    )

    @api.depends("command_ids")
    def _compute_has_payment_command(self) -> None:
        for bot in self:
            command_names = bot.command_ids.mapped("name")
            bot.has_pago_command = "/pago" in command_names
            bot.has_especie_command = "/especie" in command_names

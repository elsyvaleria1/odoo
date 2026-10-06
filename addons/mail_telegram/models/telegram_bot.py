from odoo import api, fields, models, tools


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    notify_mail = fields.Boolean(
        string="Deliver Odoo Notifications",
        help="Connected users receive their Odoo notifications and chats through "
        "this bot, and their replies are posted back.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        self.env.registry.clear_cache("mail")
        return super().create(vals_list)

    def write(self, vals):
        if "notify_mail" in vals or "active" in vals:
            self.env.registry.clear_cache("mail")
        return super().write(vals)

    def unlink(self):
        self.env.registry.clear_cache("mail")
        return super().unlink()

    @api.model
    @tools.ormcache(cache="mail")
    def _get_notifying_bot_ids(self) -> tuple[int, ...]:
        # the cache is shared by every user: the caller looks up as sudo
        bots = self.with_context(active_test=True)
        return tuple(bots.search([("notify_mail", "=", True)]).ids)

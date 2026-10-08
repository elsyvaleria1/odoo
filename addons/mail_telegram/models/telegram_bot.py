from odoo import api, fields, models, tools

from odoo.addons.telegram.tools.authority import keeping, operating


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
    def _command_menu_fields(self) -> set:
        return super()._command_menu_fields() | {"notify_mail"}

    @api.model
    @tools.ormcache(cache="mail")
    def _get_notifying_bot_ids(self) -> tuple[int, ...]:
        # one answer for every caller, so read past the company guard that
        # would make it the first caller's: which bots deliver is the bots'
        # own configuration
        bots = keeping(self).with_context(active_test=True)
        return tuple(bots.search([("notify_mail", "=", True)]).ids)

    @api.model
    def _get_notifying_bots(self, user):
        """The bots delivering `user`'s notifications: those that deliver any
        and serve a company of theirs, where their replies are heard.
        Read as `user`, in their companies: the answer is theirs, whoever
        asks -- a poster of another company, the outbox, the webhook."""
        bots = operating(
            self.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)
        )
        # a bot of a company not theirs is beyond their reach: it is weighed
        # where the bots are kept, or reading its company refuses them all
        admitted = (
            keeping(self)
            .browse(self._get_notifying_bot_ids())
            .exists()
            .filtered(lambda bot: bot._admits_user(user))
        )
        return bots.browse(admitted.ids)

    def _get_mail_refusal(self, account, user) -> str | None:
        """Why this bot may not carry `user`'s Odoo mail to the Telegram
        `account`, in words for that user; None when it may."""
        self.check_singleton()
        if not self._admits_user(user):
            return self.env._(
                "This bot serves %(companies)s, none of them a company you belong to.",
                companies=", ".join(keeping(self).company_ids.mapped("name")),
            )
        if not account or account._acting_user("internal") != user:
            return self.env._("This Telegram account is not connected to you.")
        return None

    def _can_deliver_mail(self, account, user) -> bool:
        return self._get_mail_refusal(account, user) is None

    def _is_phone_needed_for_mail(self, account, user) -> bool:
        """Whether sharing the account's phone number is what stands between
        it and `user`'s Odoo mail."""
        return False

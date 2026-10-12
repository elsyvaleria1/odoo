from odoo import api, fields, models, tools
from odoo.fields import Domain

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
        if vals.keys() & {"notify_mail", "active", "moved_to_id", "credential_id"}:
            self.env.registry.clear_cache("mail")
        return super().write(vals)

    def _handle_on_air_change(self) -> None:
        super()._handle_on_air_change()
        self.env.registry.clear_cache("mail")

    def unlink(self):
        self.env.registry.clear_cache("mail")
        return super().unlink()

    @api.model
    def _command_menu_fields(self) -> set:
        return super()._command_menu_fields() | {"notify_mail"}

    @api.model
    @tools.ormcache(cache="mail")
    def _get_notifying_bot_ids(self) -> tuple[int, ...]:
        bots = keeping(self).with_context(active_test=True)
        return tuple(
            bots.search(
                Domain("notify_mail", "=", True) & bots._get_delivering_domain()
            ).ids
        )

    @api.model
    def _get_notifying_bots(self, user):
        bots = operating(
            self.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)
        )
        admitted = (
            keeping(self)
            .browse(self._get_notifying_bot_ids())
            .exists()
            .filtered(lambda bot: bot._admits_user(user))
        )
        return bots.browse(admitted.ids)

    def _get_mail_refusal(self, account, user) -> str | None:
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
        return False

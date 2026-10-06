from odoo import fields, models


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    notify_company_phones_only = fields.Boolean(
        string="Only to Company Phones",
        help="Odoo notifications reach a user only on the Telegram account of a "
        "company phone assigned to them: one whose shared number is the number "
        "of an active Mobile Phone device whose phone user they are. Replies "
        "and the inbox follow the same rule.",
    )

    def _get_mail_refusal(self, account, user) -> str | None:
        refusal = super()._get_mail_refusal(account, user)
        if refusal or not self.notify_company_phones_only:
            return refusal
        if not account.phone_digits:
            return self.env._(
                "Your Odoo notifications reach only the Telegram of your company "
                "phone: share this account's phone number to show it is that one."
            )
        if account.phone_digits not in self._get_company_phone_digits(user):
            return self.env._(
                "%(phone)s is not the number of a company phone assigned to you. "
                "Ask an administrator to record your phone in Devices.",
                phone=account.phone,
            )
        return None

    def _is_phone_needed_for_mail(self, account, user) -> bool:
        return bool(
            self.notify_company_phones_only and account and not account.phone_digits
        )

    def _get_company_phone_digits(self, user) -> set[str]:
        """The last digits of the numbers of the company phones `user`
        carries, in the company this bot speaks for."""
        self.check_singleton()
        category = self.env.ref("device_mobile.device_category_mobile_phone")
        # read as `user` in this bot's company, whoever asks: the poster's or
        # the webhook's companies decide nothing
        devices = (
            self.env["device.device"]
            .with_user(user)
            .with_context(allowed_company_ids=self.company_id.ids)
        )
        devices = devices.with_privilege(
            "device_mobile_telegram.privilege_read_company_phones",
            reason="a bot compares a Telegram account's number with the company "
            "phones of the user it would deliver to",
        )
        phones = devices.search(
            [
                ("user_id", "=", user.id),
                ("device_category_id", "=", category.id),
                ("line_number_digits", "!=", False),
                ("company_id", "in", [self.company_id.id, False]),
            ]
        )
        return set(phones.mapped("line_number_digits"))

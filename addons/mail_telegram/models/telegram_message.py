from odoo import api, fields, models


class TelegramMessage(models.Model):
    _inherit = "telegram.message"

    mail_message_id = fields.Many2one(
        comodel_name="mail.message",
        index="btree_not_null",
        ondelete="cascade",
        help="The Odoo message this Telegram message carries: sent as a "
        "notification, or posted from a reply.",
    )
    recipient_partner_id = fields.Many2one(
        comodel_name="res.partner",
        ondelete="cascade",
        help="Whose notification it is.",
    )
    mail_away_only = fields.Boolean(
        string="Only While Away",
        help="Sent only if its recipient is not online in Odoo when it is due.",
    )
    mail_company_id = fields.Many2one(
        comodel_name="res.company",
        ondelete="cascade",
        help="The company of the record the notification is about, whose bot "
        "carries it.",
    )

    @api.model
    def _gc_removable_domain(self, now) -> list:
        return [("mail_message_id", "=", False), *super()._gc_removable_domain(now)]

    def _still_wanted(self) -> bool:
        if not super()._still_wanted():
            return False
        if not self.mail_message_id or not self.recipient_partner_id:
            return True
        partner = self.recipient_partner_id
        user = self._get_recipient_user()
        if (
            not user
            or user._get_telegram_notify_chat(self.mail_company_id) != self.chat_id
        ):
            return False
        if self.mail_away_only and user.im_status == "online":
            return False
        message = self.mail_message_id
        if message.model == "discuss.channel":
            member = self.env["discuss.channel.member"].search(
                [("channel_id", "=", message.res_id), ("partner_id", "=", partner.id)],
                limit=1,
            )
            return not (
                member.seen_message_id and member.seen_message_id.id >= message.id
            )
        notification = self.env["mail.notification"].search(
            [("mail_message_id", "=", message.id), ("res_partner_id", "=", partner.id)],
            limit=1,
        )
        return not notification.is_read

    def _get_recipient_user(self):
        return self.recipient_partner_id.user_ids.filtered(
            lambda user: user.active and not user.share
        )[:1]

    def _on_delivery_failed(self, error, started) -> None:
        super()._on_delivery_failed(error, started)
        user = self._get_recipient_user()
        if not started or not user or not self.mail_message_id:
            return
        user._notify_telegram_unreachable(
            self.chat_id, error or self.env._("Telegram refused it.")
        )

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

    @api.model
    def _gc_removable_domain(self, now) -> list:
        # a row a mail message needs -- to route a reply, to know it was
        # delivered -- lives as long as the message does
        return [("mail_message_id", "=", False), *super()._gc_removable_domain(now)]

    def _still_wanted(self) -> bool:
        """A notification already read in Odoo, or due while its recipient
        is online and asked for Telegram only while away, is not sent."""
        if not super()._still_wanted():
            return False
        if not self.mail_message_id or not self.recipient_partner_id:
            return True
        partner = self.recipient_partner_id
        user = partner.user_ids.filtered(lambda u: u.active and not u.share)[:1]
        if not user or self.chat_id.account_id._acting_user("internal") != user:
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

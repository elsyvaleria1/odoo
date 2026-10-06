from odoo import models


class MixinTelegramHandler(models.AbstractModel):
    _inherit = "mixin.telegram.handler"

    def _link_inbound(self, bot, chat, message, posted) -> None:
        """Record on the message's inbound ledger row the Odoo message it was
        posted as: an edit or a reply to it finds it there."""
        if not message.get("message_id"):
            return
        self.env["telegram.message"].search(
            [
                ("bot_id", "=", bot.id),
                ("chat_id", "=", chat.id),
                ("msg_uid", "=", str(message["message_id"])),
                ("message_type", "=", "inbound"),
            ],
            limit=1,
        ).write({"mail_message_id": posted.id})

    @staticmethod
    def _react(posted, partner, added, removed) -> None:
        """`partner`'s reactions to an Odoo message follow theirs in
        Telegram."""
        # reactions are mail's own records: whoever answers for the person
        # reacts in their name, as a post would be
        message = posted.with_privilege(
            "mail.privilege_post_as_author",
            reason="a reaction in Telegram is its person's in Odoo",
        )
        guest = message.env["mail.guest"]
        for content in added:
            message._message_reaction(content, "add", partner, guest)
        for content in removed:
            message._message_reaction(content, "remove", partner, guest)

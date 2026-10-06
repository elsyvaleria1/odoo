from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    livechat_channel_id = fields.Many2one(
        comodel_name="im_livechat.channel",
        string="Live Chat Channel",
        help="Customers -- anyone who is not an Odoo user -- writing to this bot "
        "are answered in a session of this Live Chat channel.",
    )
    livechat_chatbot_script_id = fields.Many2one(
        comodel_name="chatbot.script",
        string="Chatbot",
        help="The script that greets a customer on a new session, when no "
        "operator should answer first. It must be one of the channel's rules.",
    )
    livechat_operator_label = fields.Boolean(
        string="Show Operator Names",
        default=True,
        help="Prefix operators' messages with their name. Off, customers see the "
        "bot speaking for the company.",
    )
    livechat_waiting_message = fields.Char(
        string="Message While Nobody Is Online",
        translate=True,
        help="Sent to a customer whose session opens with no operator online.",
    )

    @api.constrains("livechat_channel_id", "livechat_chatbot_script_id")
    def _check_livechat_chatbot(self) -> None:
        for bot in self:
            script = bot.livechat_chatbot_script_id
            if (
                script
                and script not in bot.livechat_channel_id.rule_ids.chatbot_script_id
            ):
                raise ValidationError(
                    self.env._(
                        "The chatbot of bot %(bot)s must be one of its Live Chat "
                        "channel's rules.",
                        bot=bot.name,
                    )
                )

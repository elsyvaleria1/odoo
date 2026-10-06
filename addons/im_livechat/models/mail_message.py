from odoo import models
from odoo.libs.debug_log import DebugLog

from odoo.addons.mail.tools.discuss import Store

_debug = DebugLog(__name__)

FREE_INPUT_STEP_TYPES = (
    "free_input_multi",
    "free_input_single",
    "question_email",
    "question_phone",
)


class MailMessage(models.Model):
    _inherit = "mail.message"

    def _to_store_defaults(self, target):
        return super()._to_store_defaults(target) + ["chatbot_current_step"]

    def _to_store(self, store: Store, fields, **kwargs) -> None:
        super()._to_store(
            store, [f for f in fields if f != "chatbot_current_step"], **kwargs
        )
        if "chatbot_current_step" not in fields:
            return
        channel_messages = self.filtered(lambda message: message.channel_id)
        channel_by_message = channel_messages._record_by_message()
        chatbot_channels = (
            self.env["discuss.channel"]
            .union(*channel_by_message.values())
            .filtered(
                lambda channel: (
                    channel.channel_type == "livechat"
                    and channel.chatbot_current_step_id
                )
            )
        )
        chatbot_by_channel = {
            channel: channel.chatbot_current_step_id.chatbot_script_id.operator_partner_id
            for channel in chatbot_channels.sudo()
        }
        bot_messages = self.browse(
            message.id
            for message in channel_messages
            if channel_by_message[message] in chatbot_by_channel
            and message.author_id == chatbot_by_channel[channel_by_message[message]]
        )
        if not bot_messages:
            return
        chatbot_messages = (
            self.env["chatbot.message"]
            .sudo()
            .search([("mail_message_id", "in", bot_messages.ids)])
        )
        chatbot_message_by_message = {
            chatbot_message.mail_message_id: chatbot_message
            for chatbot_message in chatbot_messages
        }
        free_input_steps = chatbot_messages.script_step_id.filtered(
            lambda step: step.step_type in FREE_INPUT_STEP_TYPES
        )
        user_answers = self.env["chatbot.message"]
        if free_input_steps:
            user_answers = (
                self.env["chatbot.message"]
                .sudo()
                .search(
                    [
                        ("script_step_id", "in", free_input_steps.ids),
                        (
                            "discuss_channel_id",
                            "in",
                            chatbot_messages.discuss_channel_id.ids,
                        ),
                    ],
                )
            )
        _debug.perf.count(
            "chatbot_steps_to_store",
            messages=len(bot_messages),
            chatbot_messages=len(chatbot_messages),
            user_answers=len(user_answers),
        )
        for message in bot_messages:
            chatbot_message = chatbot_message_by_message.get(message)
            if not chatbot_message or not (step := chatbot_message.script_step_id):
                continue
            channel = channel_by_message[message]
            chatbot = chatbot_by_channel[channel]
            step_data = {
                "id": (step.id, message.id),
                "message": message.id,
                "scriptStep": Store.One(step, ["id", "message", "step_type"]),
                "operatorFound": step.is_forward_operator
                and channel.livechat_operator_id != chatbot,
            }
            if answer := chatbot_message.user_script_answer_id:
                step_data["selectedAnswer"] = {
                    "id": answer.id,
                    "label": answer.name,
                }
            if step in free_input_steps:
                user_answer_message = next(
                    (
                        user_answer
                        for user_answer in user_answers
                        if user_answer.script_step_id == step
                        and user_answer.discuss_channel_id == channel
                        and user_answer != chatbot_message
                    ),
                    self.env["chatbot.message"],
                )
                step_data["rawAnswer"] = [
                    "markup",
                    user_answer_message.user_raw_answer,
                ]
            store.add_model_values("ChatbotStep", step_data)
            store.add(
                message,
                {"chatbotStep": {"scriptStep": step.id, "message": message.id}},
            )

    def _get_store_partner_name_fields(self):
        if self.channel_id.channel_type == "livechat":
            return self.env["res.partner"]._get_fields_store_livechat_username()
        return super()._get_store_partner_name_fields()

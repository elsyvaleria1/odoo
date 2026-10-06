from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.mail.tools.discuss import Store, add_guest_to_context

_debug = DebugLog(__name__)


class LivechatChatbotScriptController(http.Controller):
    def _get_livechat_session(self, channel_id):
        return request.env["discuss.channel"].search(
            [("id", "=", channel_id), ("channel_type", "=", "livechat")]
        )

    def _get_replayable_chatbot(self, discuss_channel, chatbot_script_id):
        chatbot = discuss_channel._get_session_chatbot_script(chatbot_script_id)
        if not chatbot:
            _debug.logic(
                "chatbot_replay_refused",
                channel=discuss_channel.id,
                script=chatbot_script_id,
                reason="not_the_session_script",
            )
            return request.env["chatbot.script"]
        if discuss_channel.sudo().livechat_agent_history_ids:
            _debug.logic(
                "chatbot_replay_refused",
                channel=discuss_channel.id,
                script=chatbot_script_id,
                reason="agent_joined",
            )
            return request.env["chatbot.script"]
        return chatbot

    @http.route("/chatbot/restart", type="jsonrpc", auth="public")
    @add_guest_to_context
    def chatbot_restart(self, channel_id, chatbot_script_id):
        discuss_channel = self._get_livechat_session(channel_id)
        if not discuss_channel:
            return None
        chatbot = self._get_replayable_chatbot(discuss_channel, chatbot_script_id)
        if not chatbot:
            return None
        chatbot_language = chatbot._get_chatbot_language()
        message = discuss_channel.with_context(lang=chatbot_language)._chatbot_restart(
            chatbot
        )
        return {
            "message_id": message.id,
            "store_data": Store().add(message).get_result(),
        }

    @http.route("/chatbot/answer/save", type="jsonrpc", auth="public")
    @add_guest_to_context
    def chatbot_save_answer(self, channel_id, message_id, selected_answer_id):
        discuss_channel = self._get_livechat_session(channel_id)
        chatbot_message = (
            request.env["chatbot.message"]
            .sudo()
            .search(
                [
                    ("mail_message_id", "=", message_id),
                    ("discuss_channel_id", "=", discuss_channel.id),
                ],
                limit=1,
            )
        )
        selected_answer = (
            request.env["chatbot.script.answer"].sudo().browse(selected_answer_id)
        )

        if not discuss_channel or not chatbot_message or not selected_answer.exists():
            return

        if selected_answer in chatbot_message.script_step_id.answer_ids:
            chatbot_message.write({"user_script_answer_id": selected_answer_id})

    @http.route("/chatbot/step/trigger", type="jsonrpc", auth="public")
    @add_guest_to_context
    def chatbot_trigger_step(self, channel_id, chatbot_script_id=None, data_id=None):
        chatbot_language = self.env["chatbot.script"]._get_chatbot_language()
        discuss_channel = self._get_livechat_session(channel_id).with_context(
            lang=chatbot_language
        )
        if not discuss_channel:
            return
        partner, guest = self.env["res.partner"]._get_current_persona()
        store = Store(bus_channel=partner or guest)
        store.data_id = data_id

        chatbot = discuss_channel.sudo().chatbot_current_step_id.chatbot_script_id
        start = self.env["chatbot.script"]
        if not chatbot and chatbot_script_id:
            chatbot = start = self._get_replayable_chatbot(
                discuss_channel, chatbot_script_id
            ).with_context(lang=chatbot_language)
            if not chatbot:
                store.resolve_data_request()
                store.bus_send()
                return
        status, next_step, posted_message = discuss_channel._chatbot_advance(start)
        if status == "operator":
            return
        if status != "posted":
            store.resolve_data_request()
            store.bus_send()
            return
        store.add(posted_message).add(next_step)
        store.resolve_data_request(
            chatbot_step={"scriptStep": next_step.id, "message": posted_message.id}
        )
        chatbot_next_step_id = (next_step.id, posted_message.id)
        store.add_model_values(
            "ChatbotStep",
            {
                "id": chatbot_next_step_id,
                "isLast": next_step._is_last_step(discuss_channel),
                "message": posted_message.id,
                "operatorFound": next_step.is_forward_operator
                and discuss_channel.livechat_operator_id != chatbot.operator_partner_id,
                "scriptStep": next_step.id,
            },
        )
        store.add_model_values(
            "Chatbot",
            {
                "currentStep": {
                    "id": chatbot_next_step_id,
                    "scriptStep": next_step.id,
                    "message": posted_message.id,
                },
                "id": (chatbot.id, discuss_channel.id),
                "script": chatbot.id,
                "thread": Store.One(discuss_channel, [], as_thread=True),
                "steps": [
                    (
                        "ADD",
                        [
                            {
                                "scriptStep": chatbot_next_step_id[0],
                                "message": chatbot_next_step_id[1],
                            }
                        ],
                    )
                ],
            },
        )
        store.bus_send()

    @http.route("/chatbot/step/validate_email", type="jsonrpc", auth="public")
    @add_guest_to_context
    def chatbot_validate_email(self, channel_id):
        discuss_channel = self._get_livechat_session(channel_id).with_context(
            lang=self.env["chatbot.script"]._get_chatbot_language()
        )
        if not discuss_channel or not discuss_channel.chatbot_current_step_id:
            return None

        chatbot = discuss_channel.sudo().chatbot_current_step_id.chatbot_script_id
        domain = [
            ("author_id", "!=", chatbot.operator_partner_id.id),
            ("model", "=", "discuss.channel"),
            ("res_id", "=", channel_id),
        ]
        last_user_message = (
            self.env["mail.message"].sudo().search(domain, order="id desc", limit=1)
        )
        result = {}
        if last_user_message:
            result = chatbot._get_email_check(last_user_message.body, discuss_channel)
            if posted_message := result.pop("posted_message"):
                store = Store().add(posted_message)
                store.add(
                    discuss_channel,
                    {"messages": Store.Many(posted_message, mode="ADD")},
                )
                result["data"] = store.get_result()
        return result

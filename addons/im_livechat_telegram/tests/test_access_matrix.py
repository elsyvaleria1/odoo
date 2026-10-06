from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestImLivechatTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "livechat_user_a": Persona("im_livechat.im_livechat_group_user"),
        "livechat_manager_a": Persona("im_livechat.im_livechat_group_manager"),
    }
    cells = (
        Cell(
            "discuss.channel",
            "session",
            note="a Telegram customer's session is kept under a privilege",
            livechat_user_a="r",
            livechat_manager_a="r",
        ),
        Cell(
            "mail.message",
            "message",
            finding="mail.message decides by its document in _check_access, which "
            "its rows' domain and explanation do not follow",
            livechat_user_a="rc",
            livechat_manager_a="rc",
            today={
                "employee_a": {"check": "", "filter": "wcd", "explain": "rwcd"},
                "livechat_user_a": {
                    "check": "rc",
                    "filter": "rwcd",
                    "explain": "rwcd",
                },
                "livechat_manager_a": {
                    "check": "rc",
                    "filter": "rwcd",
                    "explain": "rwcd",
                },
            },
        ),
        Cell(
            "im_livechat.channel.member.history",
            "history",
            livechat_user_a="r",
            livechat_manager_a="r",
        ),
        Cell("chatbot.message", "chatbot_message", livechat_manager_a="rwcd"),
        Cell("chatbot.script.step", "step", livechat_manager_a="rwcd"),
        Cell("chatbot.script.answer", "answer", livechat_manager_a="rwcd"),
    )

    @classmethod
    def build(cls):
        script = cls.env["chatbot.script"].create({"title": "matrix bot"})
        step = cls.env["chatbot.script.step"].create(
            {
                "step_type": "question_selection",
                "message": "matrix question",
                "chatbot_script_id": script.id,
            }
        )
        answer = cls.env["chatbot.script.answer"].create(
            {"name": "matrix answer", "script_step_id": step.id}
        )
        livechat = cls.env["im_livechat.channel"].create({"name": "matrix"})
        operator = cls.env.user.partner_id
        session = cls.env["discuss.channel"].create(
            {
                "name": "matrix session",
                "channel_type": "livechat",
                "livechat_channel_id": livechat.id,
                "livechat_operator_id": operator.id,
                "channel_member_ids": [
                    Command.create(
                        {"partner_id": operator.id, "livechat_member_type": "agent"}
                    )
                ],
            }
        )
        message = session.message_post(body="matrix message")
        return {
            "session": session,
            "message": message,
            "history": session.channel_member_ids.livechat_member_history_ids[:1],
            "chatbot_message": cls.env["chatbot.message"].create(
                {
                    "discuss_channel_id": session.id,
                    "script_step_id": step.id,
                    "mail_message_id": message.id,
                }
            ),
            "step": step,
            "answer": answer,
        }

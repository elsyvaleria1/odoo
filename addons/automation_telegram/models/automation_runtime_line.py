from odoo import models
from odoo.exceptions import UserError

from .automation_telegram_wait import ANSWER_KINDS
from odoo.addons.automation.models.workflow_edge import EVENT_CONDITIONS


class AutomationRuntimeLine(models.Model):
    _inherit = "automation.runtime.line"

    def _telegram_send_and_wait(
        self, chat, text, event_code, accept=("text",), *, html=False, reply_markup=None
    ):
        self.check_singleton()
        chat.check_singleton()
        if self.state != "in_progress":
            raise UserError(
                self.env._("Only a step while it runs can ask on Telegram.")
            )
        if chat.chat_type != "private":
            raise UserError(
                self.env._(
                    "Step %(step)s asks in %(chat)s, which is not a private "
                    "chat: in a group anyone could answer.",
                    step=self.name,
                    chat=chat.display_name,
                )
            )
        kinds = [accept] if isinstance(accept, str) else list(accept)
        if not kinds or not set(kinds) <= set(ANSWER_KINDS):
            raise UserError(
                self.env._(
                    "Step %(step)s waits for %(given)s; an answer on Telegram is "
                    "one of %(known)s.",
                    step=self.name,
                    given=", ".join(kinds) or self.env._("nothing"),
                    known=", ".join(ANSWER_KINDS),
                )
            )
        if not any(
            edge.condition in EVENT_CONDITIONS and edge.event_code == event_code
            for edge in self.edge_out_ids
        ):
            raise UserError(
                self.env._(
                    "Step %(step)s asks on Telegram for event %(event)s, but no "
                    "edge leaving it waits for that event: the answer would "
                    "lead nowhere. Add an On Event edge named %(event)s.",
                    step=self.name,
                    event=event_code,
                )
            )
        prompt = chat.bot_id._queue_text(
            chat, text, html=html, reply_markup=reply_markup
        )
        wait = self.env["automation.telegram.wait"].create(
            {
                "line_id": self.id,
                "event_code": event_code,
                "chat_id": chat.id,
                "accepted_kinds": ",".join(kinds),
                "prompt_message_id": prompt.id,
            }
        )
        self._set_output(
            {
                **(self.output or {}),
                "telegram_chat_id": chat.id,
                "telegram_wait_id": wait.id,
            },
            summary=self.env._("Asked on Telegram; waiting for %s", ", ".join(kinds)),
        )
        return wait

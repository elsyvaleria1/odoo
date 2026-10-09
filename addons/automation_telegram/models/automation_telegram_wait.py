import base64
import logging
import mimetypes
from datetime import timedelta

import psycopg

from odoo import api, fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import UserError, ValidationError
from odoo.tools import frozendict

from odoo.addons.automation.models.workflow_edge import EVENT_CONDITIONS
from odoo.addons.telegram.tools.authority import operating

_logger = logging.getLogger(__name__)

# What an answer can be, in the router's own words (`message_kind`).
ANSWER_KINDS = ("text", "photo", "document", "voice", "contact", "location")
# The files of a message, by kind: the largest size of a photo, a file under
# the name it was sent with.
_FILE_KEYS = ("photo", "document", "video", "voice", "audio")
_DEFAULT_NAMES = {
    "photo": "photo.jpg",
    "document": "document",
    "video": "video.mp4",
    "voice": "voice.ogg",
    "audio": "audio",
}
# A failed delivery is tried again past these delays, in minutes, the last one
# repeating; past MAX_ATTEMPTS the answer is given up and the run says why. A
# transaction lost to a concurrent one is tried again after the first delay.
RETRY_MINUTES = (1, 2, 4, 8)
MAX_ATTEMPTS = 5
OPEN_RUN_STATES = ("in_progress", "waiting_resume")


def _lost_to_concurrency(error) -> bool:
    """Whether `error`, or one it was raised while handling, is a transaction
    lost to a concurrent one, or a statement refused because an earlier one of
    the transaction failed. Neither says anything of the answer itself: a step
    may catch the first and leave only the second to be seen."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(
            error, (*PG_RETRY_EXCEPTIONS, psycopg.errors.InFailedSqlTransaction)
        ):
            return True
        error = error.__cause__ or error.__context__
    return False


class AutomationTelegramWait(models.Model):
    """A question a workflow step asked on Telegram, and its answer.

    The step that asks settles at once; what waits is its On Event edge. This
    record is what ties a message arriving in the chat to that edge: it names
    the chat, the kinds of message that answer, and the event the answer
    delivers. The webhook only records the answer; the dispatcher delivers it,
    so no step ever runs as the person who answered.
    """

    _name = "automation.telegram.wait"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("line_id.runtime_id.company_ids", shared=False),
        }
    )
    _description = "Workflow Question on Telegram"
    _order = "id desc"

    line_id = fields.Many2one(
        comodel_name="automation.runtime.line",
        string="Asking Step",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    runtime_id = fields.Many2one(
        related="line_id.runtime_id",
    )
    event_code = fields.Char(
        string="Event",
        readonly=True,
        required=True,
        help="The event the answer delivers to the asking step: its On Event "
        "edge runs, its Without Event edge for the same event does not.",
    )
    chat_id = fields.Many2one(
        comodel_name="telegram.chat",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    bot_id = fields.Many2one(
        related="chat_id.bot_id",
    )
    accepted_kinds = fields.Char(
        readonly=True,
        required=True,
        help="Comma-separated kinds of message that answer: text, photo, "
        "document, voice, contact, location.",
    )
    prompt_message_id = fields.Many2one(
        comodel_name="telegram.message",
        string="Question",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
    )
    state = fields.Selection(
        selection=[
            ("waiting", "Waiting"),
            ("received", "Answered"),
            ("delivered", "Delivered"),
            ("cancelled", "Cancelled"),
            ("error", "Failed"),
        ],
        default="waiting",
        readonly=True,
        required=True,
        help="Waiting: no answer yet.\n"
        "Answered: the answer arrived; the dispatcher has yet to hand it on.\n"
        "Delivered: the asking step received its event.\n"
        "Cancelled: the run ended before an answer came.\n"
        "Failed: the answer could not be delivered, however often it was "
        "tried.",
    )
    reply_kind = fields.Char(readonly=True)
    reply_text = fields.Text(readonly=True)
    reply_msg_uid = fields.Char(
        string="Answer Message ID",
        readonly=True,
    )
    reply_payload = fields.Json(
        readonly=True,
        help="What of the answer the dispatcher still needs: its files' "
        "Telegram ids, a contact or a location.",
    )
    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        string="Files",
        readonly=True,
    )
    date_received = fields.Datetime(readonly=True)
    date_delivered = fields.Datetime(readonly=True)
    attempts = fields.Integer(readonly=True)
    error_message = fields.Char(readonly=True)

    _waiting_chat_idx = models.Index("(chat_id) WHERE state = 'waiting'")

    @api.constrains("accepted_kinds")
    def _check_accepted_kinds(self) -> None:
        for wait in self:
            kinds = wait._get_accepted_kinds()
            unknown = sorted(set(kinds) - set(ANSWER_KINDS))
            if not kinds or unknown:
                raise ValidationError(
                    self.env._(
                        "A question on Telegram is answered by %(known)s; "
                        "%(given)s is not one of them.",
                        known=", ".join(ANSWER_KINDS),
                        given=", ".join(unknown) or self.env._("nothing"),
                    )
                )

    @api.model
    def _cron_deliver_answers(self) -> int:
        """Hand each recorded answer to its step, and let go of the questions
        whose run ended unanswered."""
        stale = self.search([("state", "=", "waiting")]).filtered(
            lambda wait: not wait._is_live()
        )
        stale.state = "cancelled"
        delivered = 0
        for wait in self.search([("state", "=", "received")], order="id"):
            try:
                with self.env.cr.savepoint():
                    wait._deliver()
                delivered += 1
            except Exception as error:
                _logger.exception("Telegram answer %s could not be delivered", wait.id)
                concurrent = _lost_to_concurrency(error)
                wait._record_failure(error, concurrent=concurrent)
                if concurrent:
                    # this transaction's snapshot predates the one it lost to:
                    # the next answers go to a fresh run of the job
                    break
        return delivered

    def _get_accepted_kinds(self) -> list[str]:
        self.check_singleton()
        kinds = (self.accepted_kinds or "").split(",")
        return [kind.strip() for kind in kinds if kind.strip()]

    def _accepts(self, kind) -> bool:
        return kind in self._get_accepted_kinds()

    def _is_live(self) -> bool:
        """Whether an answer would still be heard: the run is open and the
        asking step's edge for this event has neither received it nor been
        closed by another branch."""
        self.check_singleton()
        if self.state != "waiting" or self.runtime_id.state not in OPEN_RUN_STATES:
            return False
        return any(
            edge.condition in EVENT_CONDITIONS
            and edge.event_code == self.event_code
            and not edge.date_event
            and not edge.revoked
            for edge in self.line_id.edge_out_ids
        )

    @api.model
    def _find_for_message(self, chat, message, kind):
        """`(wait, refused)`: the open question `message` answers in `chat`,
        and the one it was a reply to but cannot answer, being of another
        kind. A reply to a question goes to that question; any other message
        to the latest question that takes its kind."""
        waits = self.search(
            [("chat_id", "=", chat.id), ("state", "=", "waiting")]
        ).filtered(lambda wait: wait._is_live())
        if not waits:
            return self, self
        reply_to = message.get("reply_to_message") or {}
        replied_uid = str(reply_to.get("message_id") or "")
        replied = (
            waits.filtered(
                lambda wait: (
                    wait.prompt_message_id
                    and operating(wait.prompt_message_id).msg_uid == replied_uid
                )
            )
            if replied_uid
            else self
        )
        if replied:
            accepting = replied.filtered(lambda wait: wait._accepts(kind))
            return accepting[:1], (replied - accepting)[:1]
        return waits.filtered(lambda wait: wait._accepts(kind))[:1], self

    def _record_answer(self, message, kind) -> None:
        """Keep what the answer is, for the dispatcher to hand on."""
        self.check_singleton()
        payload = {"files": self._file_ids_of(message)}
        if message.get("contact"):
            payload["contact"] = message["contact"]
        if message.get("location"):
            payload["location"] = message["location"]
        self.write(
            {
                "state": "received",
                "reply_kind": kind,
                "reply_text": message.get("text") or message.get("caption") or False,
                "reply_msg_uid": str(message.get("message_id") or "") or False,
                "reply_payload": payload,
                "date_received": fields.Datetime.now(),
            }
        )
        self.env["ir.cron"]._trigger_ref("automation_telegram.ir_cron_deliver_answers")

    @staticmethod
    def _file_ids_of(message) -> list[list[str]]:
        files = []
        for key in _FILE_KEYS:
            item = message.get(key)
            if not item:
                continue
            if key == "photo":
                item = item[-1]
            name = item.get("file_name") or _DEFAULT_NAMES[key]
            files.append([item["file_id"], name])
        return files

    def _deliver(self) -> None:
        """Fetch the answer's files onto the run, make the answer the asking
        step's output, and deliver its event."""
        self.check_singleton()
        line = self.line_id
        runtime = self.runtime_id
        attachments = self.env["ir.attachment"]
        for file_id, name in (self.reply_payload or {}).get("files", []):
            downloaded = self.bot_id.get_file(file_id)
            if not downloaded:
                raise UserError(
                    self.env._("Telegram did not hand over the file %s.", name)
                )
            # a photo's name is Telegram's stored one, which carries the extension
            if name == _DEFAULT_NAMES["photo"]:
                name = downloaded["file_path"].rsplit("/", 1)[-1] or name
            attachments |= attachments.create(
                {
                    "name": name,
                    "datas": base64.b64encode(downloaded["content"]),
                    "mimetype": mimetypes.guess_type(name)[0] or False,
                    "res_model": runtime._name,
                    "res_id": runtime.id,
                }
            )
        answer = {
            "kind": self.reply_kind,
            "text": self.reply_text or "",
            "attachment_ids": attachments.ids,
            "chat_id": self.chat_id.id,
            "message_id": self.reply_msg_uid or "",
            "date": fields.Datetime.to_string(self.date_received),
        }
        for key in ("contact", "location"):
            if key in (self.reply_payload or {}):
                answer[key] = self.reply_payload[key]
        line._set_output(
            {**(line.output or {}), "answer": answer},
            summary=self.env._("Answered on Telegram (%s)", self.reply_kind),
        )
        self.write(
            {
                "state": "delivered",
                "attachment_ids": [fields.Command.set(attachments.ids)],
                "date_delivered": fields.Datetime.now(),
                "error_message": False,
            }
        )
        line._receive_event(self.event_code)

    def _record_failure(self, error, concurrent=False) -> None:
        self.check_singleton()
        attempts = self.attempts + 1
        failed = attempts >= MAX_ATTEMPTS
        self.write(
            {
                "attempts": attempts,
                "error_message": str(error),
                "state": "error" if failed else "received",
            }
        )
        if not failed:
            minutes = RETRY_MINUTES[
                0 if concurrent else min(attempts, len(RETRY_MINUTES)) - 1
            ]
            self.env.ref("automation_telegram.ir_cron_deliver_answers")._trigger(
                fields.Datetime.now() + timedelta(minutes=minutes)
            )
        else:
            self.runtime_id.message_post(
                body=self.env._(
                    "The answer to step %(step)s on Telegram could not be "
                    "delivered: %(error)s",
                    step=self.line_id.name,
                    error=str(error),
                ),
            )

import logging
import re
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models
from odoo.tools import remove_accents

from ..services import catalog, documents, files, write_ops
from ..services.catalog import NotFound, available_queries
from ..services.insight_agent import InsightAgent
from ..services.insight_assistant import HELP, SEND_DOCUMENT, InsightAssistant
from ..services.odoo_reader import OdooReader
from ..services.odoo_tools import OdooTools
from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.authority import keeping, operating
from odoo.addons.telegram.tools.dispatch import translation_env

_logger = logging.getLogger(__name__)

HISTORY_KEY = "telegram_insight_history"
# Follow-up questions ("and last month?") lean on the last exchanges; an old
# conversation is forgotten so a new question starts clean.
HISTORY_SIZE = 6
HISTORY_TTL = timedelta(hours=6)
DEFAULT_TZ = "America/Mexico_City"
# Below Telegram's 4096 so a chunk never needs truncating once tags are added.
CHUNK_LIMIT = 3800
AGENT = "agent"
PENDING_KEY = "telegram_insight_pending"
# changes not authorized within this long are dropped
PENDING_TTL = timedelta(hours=1)
_AUTHORIZE_WORDS = ("autoriz", "authoriz", "confirmo", "apruebo")
_CANCEL_WORDS = ("cancel", "no autoriz", "descart")
# below this, the classifier doubts its report answers the question
CONFIDENCE_FLOOR = 0.6
_BOLD = re.compile(r"\*\*(.+?)\*\*")


class TelegramChat(models.Model):
    _inherit = "telegram.chat"

    @api.job(channel="telegram_insight", max_retries=0, idle_timeout=900)
    def _insight_answer(self, bot_id, message, company_id) -> None:
        """Answer the question a message carries, as text or voice, in this
        chat.

        :param int bot_id: the bot the message reached
        :param dict message: the Telegram message
        :param int company_id: the company the bot acts in for the asker
        """
        self.check_singleton()
        chat = operating(self)
        bot = (
            operating(self.env["telegram.bot"])
            .browse(bot_id)
            .with_context(telegram_company_id=company_id)
        )
        tr_env = translation_env(bot, chat)
        assistant = InsightAssistant(bot)
        reader_user = keeping(bot).insight_reader_user_id
        if not assistant.available or not reader_user:
            bot.send_message(
                chat.chat_id,
                tr_env._("This bot is not set up to answer questions yet."),
            )
            return

        question = (message.get("text") or message.get("caption") or "").strip()
        attached = _files_of(message)
        if not question and not attached:
            heard = assistant.hear(chat, message)
            question = (heard.text or "").strip()
            if not question:
                bot.send_message(
                    chat.chat_id,
                    tr_env._("I could not hear the voice note. Please type it."),
                )
                return
        if not question:
            question = tr_env._("Analyse the file(s) I sent.")

        pending = chat._insight_pending()
        decision = _decision(question) if pending else None
        if decision:
            answer = (
                self._insight_authorize(bot, pending, tr_env)
                if decision == "authorize"
                else tr_env._("Cancelled: nothing was changed.")
            )
            chat._insight_set_pending(None)
            self._insight_reply(
                bot, chat, question, {"decision": decision}, answer, decision
            )
            return

        tz = self.env.user.tz or reader_user.tz or DEFAULT_TZ
        today = datetime.now(pytz.timezone(tz)).date()
        reader = OdooReader(
            self.env.registry,
            reader_user.id,
            context={"lang": tr_env.lang, "tz": tz},
        )
        queries = available_queries(self.env)
        interpretation, answer, answered_by, proposals = {}, "", False, []
        try:
            if attached:
                # a file needs reading: only the agent sees it
                interpretation = {
                    "query": "none",
                    "files": [name for _i, name, _m in attached],
                }
            else:
                interpretation = assistant.interpret(
                    question, chat._insight_history(), queries, today=today.isoformat()
                )
            key = interpretation["query"]
            if key == SEND_DOCUMENT:
                answer = self._insight_send_documents(
                    bot, chat, interpretation, reader_user, tr_env
                )
                answered_by = SEND_DOCUMENT
            elif key == HELP:
                answer = _help_text(tr_env, queries, InsightAgent(bot).available)
                answered_by = HELP
            elif key in queries and not _needs_agent(interpretation, bot):
                with reader.env() as env:
                    answer = catalog.answer(
                        env, queries[key], interpretation, tz=tz, today=today
                    )
                answered_by = key
            else:
                blocks = files.blocks(self._insight_download(bot, attached))
                answer, proposals = self._insight_ask_agent(
                    bot, chat, question, reader, tz, today, blocks
                )
                answered_by = AGENT if answer else False
        except Exception:
            _logger.exception("insight_telegram could not answer in chat %s", chat.id)
            bot.send_message(
                chat.chat_id,
                tr_env._("I could not answer that right now. Please try again."),
            )
            return
        if not answer:
            answer = tr_env._("I did not find what you asked for.")
        elif answered_by == AGENT:
            answer = (
                tr_env._("🔎 AI-consulted answer, please verify it.") + "\n\n" + answer
            )
        markup = None
        if proposals:
            chat._insight_set_pending(
                {
                    "operations": proposals,
                    "files": [list(item) for item in attached],
                    "at": fields.Datetime.to_string(fields.Datetime.now()),
                }
            )
            with reader.env() as env:
                summary = write_ops.describe(env, proposals)
            answer = "\n".join(
                [
                    answer,
                    "",
                    "**" + tr_env._("Changes waiting for your authorization:") + "**",
                    *summary,
                    "",
                    tr_env._(
                        "Say «autorizo» (text or voice) or press Authorize to apply them; «cancelar» discards them."
                    ),
                ]
            )
            markup = kb.confirm_cancel(
                tr_env._("✅ Authorize"), "ins_ok", tr_env._("❌ Cancel"), "ins_no"
            )
            interpretation = {**interpretation, "proposals": proposals}
        self._insight_reply(
            bot, chat, question, interpretation, answer, answered_by, markup=markup
        )

    def _insight_reply(
        self, bot, chat, question, interpretation, answer, answered_by, markup=None
    ) -> None:
        """Send the answer, remember it, and log the question."""
        chunks = _chunks(answer)
        for index, chunk in enumerate(chunks):
            last = index == len(chunks) - 1
            bot.send_message(chat.chat_id, chunk, reply_markup=markup if last else None)
        chat._insight_remember(question, interpretation, answer)
        self.env["telegram.insight.log"].with_privilege(
            "insight_telegram.privilege_log_question",
            reason="every question asked to the bot is kept, answered or not",
        ).create(
            {
                "bot_id": bot.id,
                "user_id": self.env.user.id,
                "question": question,
                "query": answered_by or False,
                "interpretation": interpretation,
                "answered": bool(answered_by),
                "answer": answer,
            }
        )

    def _insight_download(self, bot, attached) -> list:
        """``[(name, bytes, mimetype)]`` of the files a message carries."""
        downloaded = []
        for file_id, name, mimetype in attached:
            got = bot.get_file(file_id)
            if got and got.get("content"):
                downloaded.append((name, got["content"], mimetype))
        return downloaded

    def _insight_authorize(self, bot, pending, tr_env) -> str:
        """Apply the changes the person just authorized, all or none, in
        superuser mode but in their name, and say what was done."""
        requester = self.env.user
        env = self.env(user=requester.id, su=True)
        env = env(
            context={
                **env.context,
                "lang": tr_env.lang,
                "allowed_company_ids": env["res.company"].search([]).ids,
            }
        )
        try:
            touched = write_ops.apply(
                env,
                pending["operations"],
                self._insight_download(
                    bot, [tuple(item) for item in pending.get("files", [])]
                ),
                requester,
            )
        except Exception as error:
            _logger.info("insight_telegram could not apply %s", pending, exc_info=True)
            return tr_env._(
                "I could not apply the changes, so nothing was changed: %(error)s",
                error=str(error),
            )
        lines = ["**" + tr_env._("Done:") + "**"]
        for records in touched:
            for record in records[:5]:
                url = f"{record.get_base_url()}/odoo/{record._name}/{record.id}"
                lines.append(f"• {record.display_name}: {url}")
        return "\n".join(lines)

    def _insight_send_documents(self, bot, chat, interpretation, reader_user, tr_env):
        """Send the files a request for documents asks for, and say what was
        sent. Printing writes report caches, so it runs in this job's own
        transaction, as the reader in superuser mode over every company."""
        kind = interpretation.get("document_kind") or "credit_file"
        env = self.env(user=reader_user.id, su=True)
        env = env(
            context={
                **env.context,
                "lang": tr_env.lang,
                "allowed_company_ids": env["res.company"].search([]).ids,
            }
        )
        try:
            files, names = documents.collect(env, kind, interpretation)
        except NotFound as error:
            return str(error)
        if not files:
            return tr_env._("I found no file to send for that request.")
        bot.send_chat_action(chat, "upload_document")
        for filename, content in files:
            bot.send_document(chat.chat_id, content, filename)
        lines = [
            tr_env._("I sent you %(count)s file(s):", count=len(files)),
            *(f"• {filename}" for filename, _content in files),
        ]
        if len(names) > len(files):
            lines.append(
                tr_env._(
                    "%(count)s more matched; ask for one by its number.",
                    count=len(names) - len(files),
                )
            )
        return "\n".join(lines)

    def _insight_ask_agent(self, bot, chat, question, reader, tz, today, blocks=()):
        """The agent's answer to a question no report answers, with the
        changes it proposes, or nothing when the bot runs no agent."""
        agent = InsightAgent(bot)
        if not agent.available:
            return "", []
        bot.send_chat_action(chat, "typing")
        tools = OdooTools(
            reader, available_queries(self.env), tz=tz, today=today, writable=True
        )
        history = [
            exchange for exchange in chat._insight_history() if exchange.get("answer")
        ]
        answer = agent.answer(
            question,
            history,
            tools,
            tz=tz,
            today=today.isoformat(),
            on_round=lambda: bot.send_chat_action(chat, "typing"),
            files=blocks,
        )
        self._insight_send_pdfs(bot, chat, tools.pdf_requests, reader)
        return answer, tools.proposals

    def _insight_send_pdfs(self, bot, chat, requests, reader) -> None:
        """Print and send the PDFs the agent asked for, as Odoo prints them.
        Printing writes report caches, so it runs in this job's transaction,
        as the reader in superuser mode over every company."""
        if not requests:
            return
        env = self.env(user=reader.uid, su=True)
        env = env(
            context={
                **env.context,
                "allowed_company_ids": env["res.company"].search([]).ids,
            }
        )
        bot.send_chat_action(chat, "upload_document")
        for report_id, model, ids in requests:
            report = env["ir.actions.report"].browse(report_id)
            for record in env[model].browse(ids).exists():
                content, _format = env["ir.actions.report"]._render_qweb_pdf(
                    report.id, record.ids
                )
                name = (record.display_name or report.name).replace("/", "-")
                bot.send_document(chat.chat_id, content, f"{name}.pdf")

    def _insight_pending(self):
        """The changes waiting for this chat's authorization, if still fresh."""
        pending = self._get_context(PENDING_KEY)
        if not pending:
            return None
        cutoff = fields.Datetime.to_string(fields.Datetime.now() - PENDING_TTL)
        return pending if pending.get("at", "") >= cutoff else None

    def _insight_set_pending(self, pending) -> None:
        self._set_context(PENDING_KEY, pending)

    def _insight_history(self) -> list:
        """The recent questions of this chat and how each was read, oldest
        first."""
        cutoff = fields.Datetime.to_string(fields.Datetime.now() - HISTORY_TTL)
        return [
            exchange
            for exchange in self._get_context(HISTORY_KEY, [])
            if exchange.get("at", "") >= cutoff
        ]

    def _insight_remember(self, question, interpretation, answer) -> None:
        history = self._insight_history()
        history.append(
            {
                "question": question,
                "interpretation": interpretation,
                "answer": answer,
                "at": fields.Datetime.to_string(fields.Datetime.now()),
            }
        )
        self._set_context(HISTORY_KEY, history[-HISTORY_SIZE:])


def _decision(text):
    """Whether a reply authorizes or cancels the pending changes, else None."""
    words = remove_accents(text or "").lower().strip(" .!¡¿?")
    if any(words.startswith(word) for word in _CANCEL_WORDS) or words == "no":
        return "cancel"
    if any(word in words for word in _AUTHORIZE_WORDS) and len(words) <= 60:
        return "authorize"
    return None


def _files_of(message) -> list:
    """``[(file_id, name, mimetype)]`` of the photo or files a message carries."""
    found = []
    if message.get("photo"):
        photo = message["photo"][-1]
        found.append((photo["file_id"], "photo.jpg", "image/jpeg"))
    for kind in ("document", "audio", "video"):
        item = message.get(kind)
        if item:
            found.append(
                (
                    item["file_id"],
                    item.get("file_name") or kind,
                    item.get("mime_type") or "",
                )
            )
    return found


def _needs_agent(interpretation, bot):
    """Whether a question the classifier routed to a report should go to the
    agent instead: the classifier doubts the report answers it, and the bot
    runs an agent, which can still run that report and more."""
    confidence = interpretation.get("confidence")
    return (
        isinstance(confidence, int | float)
        and confidence < CONFIDENCE_FLOOR
        and InsightAgent(bot).available
    )


def _help_text(tr_env, queries, with_agent):
    """What the bot answers, for a greeting or a question about itself."""
    topics = {
        "sales": tr_env._("sales orders"),
        "pos_sales": tr_env._("counter sales"),
        "invoicing": tr_env._("invoicing"),
        "receivables": tr_env._("what customers owe"),
        "payables": tr_env._("what we owe suppliers"),
        "purchases": tr_env._("purchases"),
        "stock": tr_env._("stock"),
        "cash": tr_env._("bank and cash balances"),
        "deliveries": tr_env._("pending deliveries"),
        "production": tr_env._("production"),
        "payments": tr_env._("payments received and made"),
        "credit": tr_env._("credit and guarantees"),
        "statement": tr_env._("account statements"),
        "salaries": tr_env._("salaries"),
        "headcount": tr_env._("employees"),
    }
    listed = ", ".join(label for key, label in topics.items() if key in queries)
    lines = [
        tr_env._("Hi! Ask me about the business in your own words."),
        tr_env._("I answer exactly about: %(topics)s.", topics=listed),
    ]
    if with_agent:
        lines.append(
            tr_env._(
                "Anything else I look up in Odoo with AI, and say so in the answer."
            )
        )
    return "\n".join(
        [
            *lines,
            tr_env._(
                "For example: «how much did we sell this month by branch?» or "
                "«how much do customers owe us?»"
            ),
        ]
    )


def _as_html(text):
    return _BOLD.sub(r"<b>\1</b>", tg.escape(text))


def _chunks(text):
    """`text` as Telegram HTML messages, split between lines."""
    chunks, current = [], ""
    for line in text.split("\n"):
        line = _as_html(line)
        if len(line) > CHUNK_LIMIT:
            line = tg.truncate(line, CHUNK_LIMIT)
        if current and len(current) + len(line) + 1 > CHUNK_LIMIT:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current.strip():
        chunks.append(current)
    return chunks

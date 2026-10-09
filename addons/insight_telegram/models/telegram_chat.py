import logging
import re
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models

from ..services import catalog
from ..services.catalog import available_queries
from ..services.insight_agent import InsightAgent
from ..services.insight_assistant import HELP, InsightAssistant
from ..services.odoo_reader import OdooReader
from ..services.odoo_tools import OdooTools
from odoo.addons.telegram.tools import format as tg
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

        question = (message.get("text") or "").strip()
        if not question:
            heard = assistant.hear(chat, message)
            question = (heard.text or "").strip()
            if not question:
                bot.send_message(
                    chat.chat_id,
                    tr_env._("I could not hear the voice note. Please type it."),
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
        interpretation, answer, answered_by = {}, "", False
        try:
            interpretation = assistant.interpret(
                question, chat._insight_history(), queries, today=today.isoformat()
            )
            key = interpretation["query"]
            if key == HELP:
                answer = _help_text(tr_env, queries, InsightAgent(bot).available)
                answered_by = HELP
            elif key in queries:
                with reader.env() as env:
                    answer = catalog.answer(
                        env, queries[key], interpretation, tz=tz, today=today
                    )
                answered_by = key
            else:
                answer = self._insight_ask_agent(bot, chat, question, reader, tz, today)
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
        for chunk in _chunks(answer):
            bot.send_message(chat.chat_id, chunk)
        chat._insight_remember(question, interpretation, answer)
        self.env["telegram.insight.log"].with_privilege(
            "insight_telegram.privilege_log_question",
            reason="every question asked to the bot is kept, answered or not",
        ).create(
            {
                "bot_id": bot.id,
                "user_id": self.env.user.id,
                "question": question,
                "query": answered_by,
                "interpretation": interpretation,
                "answered": bool(answered_by),
                "answer": answer,
            }
        )

    def _insight_ask_agent(self, bot, chat, question, reader, tz, today) -> str:
        """The agent's answer to a question no report answers, or nothing
        when the bot runs no agent."""
        agent = InsightAgent(bot)
        if not agent.available:
            return ""
        bot.send_chat_action(chat, "typing")
        tools = OdooTools(reader)
        history = [
            exchange for exchange in chat._insight_history() if exchange.get("answer")
        ]
        return agent.answer(
            question,
            history,
            tools,
            tz=tz,
            today=today.isoformat(),
            on_round=lambda: bot.send_chat_action(chat, "typing"),
        )

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

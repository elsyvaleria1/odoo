import base64
import logging
import re
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.authority import in_bot_company
from odoo.addons.telegram.tools.dispatch import (
    TelegramCommand,
    log_command_execution,
    translation_env,
)

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

DEFAULT_TZ = "America/Mexico_City"

RECEIVABLE_ACCOUNT_TYPES = [
    {"id": "trade_receivable", "selected": True},
    {"id": "non_trade_receivable", "selected": True},
]

CMD_PERIOD_STATEMENT = "/estadocuentaperiodo"
CMD_CUSTOMER_STATEMENT = "/edocliente"

CALLBACK_PREFIX = "fin_period_"
CALLBACK_CUSTOM = "fin_custom"
CALLBACK_ECMANAGER = "ecm_partner_"
CALLBACK_ECM_PERIOD = "ecm_period_"
CALLBACK_ECM_CUSTOM = "ecm_custom"

_MANAGER_COMMANDS = frozenset({CMD_CUSTOMER_STATEMENT})


class TelegramHandlerAccount(models.AbstractModel):
    _name = "telegram.handler.account"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Account Statements"

    def _telegram_commands(self) -> dict:
        return {
            CMD_PERIOD_STATEMENT: TelegramCommand(
                "_handle_estadocuentaperiodo_command",
                "partner",
                description=_lt("Get your account statement"),
                company="choose",
            ),
            CMD_CUSTOMER_STATEMENT: TelegramCommand(
                "_handle_edocliente_command",
                "partner",
                starts_flow=True,
                description=_lt("Look up a customer's account statement"),
                company="choose",
            ),
        }

    def _telegram_callback_prefixes(self):
        return (
            CALLBACK_PREFIX,
            CALLBACK_CUSTOM,
            CALLBACK_ECMANAGER,
            CALLBACK_ECM_PERIOD,
            CALLBACK_ECM_CUSTOM,
        )

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("an account statement request")

    def _command_allowed(self, bot, chat, command, partner, internal_user) -> bool:
        if command in _MANAGER_COMMANDS:
            return bool(partner and chat and self._reads_any_customer(chat))
        return True

    def _explain_command_refusal(
        self, bot, chat, command, partner, internal_user
    ) -> None:
        if command in _MANAGER_COMMANDS:
            bot.send_message(chat.chat_id, self._any_customer_refusal(bot, chat))
            return
        super()._explain_command_refusal(bot, chat, command, partner, internal_user)

    @log_command_execution
    def _handle_estadocuentaperiodo_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        tr_env = translation_env(bot, chat)

        if not self._has_partner_access(bot, chat, partner):
            return

        keyboard = self._period_keyboard(tr_env, CALLBACK_PREFIX, CALLBACK_CUSTOM)

        bot.send_message(
            chat.chat_id,
            tr_env._("📅 <b>Choose the period for your account statement:</b>")
            + self._answer_hint(bot, chat),
            reply_markup=keyboard,
        )

    @log_command_execution
    def _handle_edocliente_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        if not self._check_reads_any_customer(bot, chat):
            return

        self._flow_start(chat, "ecmanager_search", {"step": "search_partner"})

        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "🔍 <b>Look up a customer account statement</b>\n\nType the name, or part of "
                "the name, of the customer you want to look up:"
            )
            + self._answer_hint(bot, chat),
        )

    def _period_keyboard(self, tr_env, prefix, custom) -> dict:

        def button(text, period):
            return {"text": text, "callback_data": f"{prefix}{period}"}

        return {
            "inline_keyboard": [
                [button(tr_env._("Current year"), "year")],
                [
                    button(tr_env._("Last month"), "1m"),
                    button(tr_env._("Last 3 months"), "3m"),
                ],
                [
                    button(tr_env._("Last 6 months"), "6m"),
                    button(tr_env._("Previous year"), "1y"),
                ],
                [{"text": tr_env._("📆 Custom"), "callback_data": custom}],
            ]
        }

    def _answer_hint(self, bot, chat):
        return ""

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        callback_data = callback_query.get("data", "")
        callback_id = callback_query.get("id")

        if callback_data.startswith(CALLBACK_ECMANAGER):
            bot.answer_callback_query(callback_id)
            self._handle_ecmanager_partner_selected(bot, chat, callback_data)
        elif (
            callback_data.startswith(CALLBACK_ECM_PERIOD)
            or callback_data == CALLBACK_ECM_CUSTOM
        ):
            bot.answer_callback_query(callback_id)
            self._handle_ecmanager_period_selected(bot, chat, callback_data)
        elif (
            not callback_data.startswith(CALLBACK_PREFIX)
            and callback_data != CALLBACK_CUSTOM
        ):
            return False
        else:
            self._handle_self_service_period_callback(
                bot, chat, callback_data, callback_id, partner
            )

        return True

    def _handle_self_service_period_callback(
        self, bot, chat, callback_data, callback_id, partner
    ) -> None:
        tr_env = translation_env(bot, chat)
        bot.answer_callback_query(callback_id)

        if not partner:
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "Your Telegram account is not connected to Odoo. In Odoo, open My "
                    "Preferences and press Connect Telegram, or ask an administrator for "
                    "an invitation."
                ),
            )
            return

        if callback_data == CALLBACK_CUSTOM:
            if self._router()._flow_guard_blocks(bot, chat, callback_data):
                return
            self._start_custom_period_flow(bot, chat)
            return

        period = callback_data.replace(CALLBACK_PREFIX, "")
        date_from, date_to = self._get_period_dates(period, self._requester_today(chat))

        if date_from and date_to:
            try:
                self._generate_and_send_report(bot, chat, partner, date_from, date_to)
            except AccessError:
                bot.send_message(
                    chat.chat_id,
                    tr_env._(
                        "You do not have permission to generate this report. "
                        "Contact the administrator."
                    ),
                )
            except Exception:
                _logger.exception("Error generating report")
                bot.send_message(
                    chat.chat_id,
                    tr_env._(
                        "An error occurred while generating the account statement. "
                        "Please try again later."
                    ),
                )

    def _requester_today(self, chat):
        company = chat.bot_id._acting_company().with_env(
            self._statement_bot(chat.bot_id).env
        )
        tz = chat.partner_id.tz or company.partner_id.tz or DEFAULT_TZ
        return fields.Date.context_today(chat.with_context(tz=tz))

    def _get_period_dates(self, period, today) -> tuple:
        if period == "year":
            date_from = date(today.year, 1, 1)
            date_to = date(today.year, 12, 31)
        elif period == "1m":
            date_to = today.replace(day=1) - relativedelta(days=1)
            date_from = date_to.replace(day=1)
        elif period == "3m":
            date_to = today.replace(day=1) - relativedelta(days=1)
            date_from = date_to.replace(day=1) - relativedelta(months=2)
        elif period == "6m":
            date_to = today.replace(day=1) - relativedelta(days=1)
            date_from = date_to.replace(day=1) - relativedelta(months=5)
        elif period == "1y":
            previous_year = today.year - 1
            date_from = date(previous_year, 1, 1)
            date_to = date(previous_year, 12, 31)
        else:
            return None, None

        return date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d")

    def _start_custom_period_flow(self, bot, chat) -> None:
        self._flow_start(chat, "estadocuenta_custom", {"step": "date_from"})

        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "📅 <b>Custom period</b>\n\nEnter the <b>start date</b> in YYYY-MM-DD "
                "format\nExample: <code>2024-01-01</code>"
            )
            + self._answer_hint(bot, chat),
        )

    def _on_message(self, bot, chat, message, partner, internal_user):
        tr_env = translation_env(bot, chat)
        context = self._flow_data(chat)
        flow = self._flow_step(chat)
        text = message.get("text", "").strip()

        if flow == "ecmanager_search":
            self._search_partners_for_ecmanager(bot, chat, text)
        elif flow == "ecmanager_custom":
            self._handle_ecmanager_custom_input(bot, chat, text, context)
        elif flow == "estadocuenta_custom":
            if not partner:
                self._flow_end(chat)
                bot.send_message(
                    chat.chat_id,
                    tr_env._(
                        "Your Telegram account is not connected to Odoo. In Odoo, open My "
                        "Preferences and press Connect Telegram, or ask an administrator for "
                        "an invitation."
                    ),
                )
            else:
                self._handle_custom_date_input(bot, chat, text, partner)
        else:
            return False
        return True

    def _handle_ecmanager_custom_input(self, bot, chat, text, context) -> None:
        tr_env = translation_env(bot, chat)

        if not self._check_reads_any_customer(bot, chat):
            return

        target_partner_id = context.get("target_partner_id")
        if not target_partner_id:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "The session has expired. Please use /edocliente to start again."
                ),
            )
            return

        target_partner = bot.env["res.partner"].browse(target_partner_id)
        if not target_partner.exists():
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "The selected customer no longer exists. Please try again with "
                    "/edocliente"
                ),
            )
            return

        self._handle_custom_date_input(
            bot, chat, text, target_partner, requester_partner=chat.partner_id
        )

    def _handle_custom_date_input(
        self, bot, chat, text, target_partner, requester_partner=None
    ) -> None:
        tr_env = translation_env(bot, chat)
        context = self._flow_data(chat)
        step = context.get("step")

        if step == "date_from":
            if self._is_date_format_valid(text):
                self._ask_end_date(bot, chat, text)
            else:
                bot.send_message(
                    chat.chat_id,
                    tr_env._(
                        "❌ Invalid date format.\nPlease use YYYY-MM-DD (example: "
                        "<code>2024-01-01</code>)"
                    ),
                )
            return

        if step == "date_to":
            if self._is_date_format_valid(text):
                date_from = context.get("date_from")
                date_to = text
                if date_from > date_to:
                    bot.send_message(
                        chat.chat_id,
                        tr_env._(
                            "❌ The end date must be later than the start date.\nStart "
                            "date: {date_from}\nPlease enter a valid end date."
                        ).format(date_from=tg.escape(date_from)),
                    )
                    return
                self._flow_end(chat)
                try:
                    self._generate_and_send_report(
                        bot,
                        chat,
                        target_partner,
                        date_from,
                        date_to,
                        requester_partner=requester_partner,
                    )
                except Exception:
                    _logger.exception("Error generating report")
                    bot.send_message(
                        chat.chat_id,
                        tr_env._(
                            "An error occurred while generating the account statement. "
                            "Please try again later."
                        ),
                    )
            else:
                bot.send_message(
                    chat.chat_id,
                    tr_env._(
                        "❌ Invalid date format.\nPlease use YYYY-MM-DD (example: "
                        "<code>2024-12-31</code>)"
                    ),
                )
            return

    def _ask_end_date(self, bot, chat, date_from) -> None:
        chat._flow_update({"date_from": date_from, "step": "date_to"})
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)
            ._(
                "✅ Start date: <b>{date_from}</b>\n\nNow enter the <b>end "
                "date</b> in YYYY-MM-DD format\nExample: <code>2024-12-31</code>"
            )
            .format(date_from=tg.escape(date_from))
            + self._answer_hint(bot, chat),
        )

    def _is_date_format_valid(self, date_str) -> bool:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
            return False
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _is_manager(self, chat) -> bool:
        user = self._chat_internal_user(chat)
        return bool(bool(user) and user.has_group("account.group_account_manager"))

    def _reads_any_customer(self, chat) -> bool:
        user = self._chat_internal_user(chat)
        return bool(user) and (
            chat.env["res.partner"].with_user(user).has_access("print_statement")
        )

    def _any_customer_refusal(self, bot, chat):
        return translation_env(bot, chat)._(
            "⛔ Only a linked Odoo user who reads customer statements in Odoo can "
            "look up another customer's account statement."
        )

    def _check_reads_any_customer(self, bot, chat) -> bool:
        if not self._reads_any_customer(chat):
            self._flow_end(chat)
            bot.send_message(chat.chat_id, self._any_customer_refusal(bot, chat))
            return False
        return True

    def _statement_bot(self, bot):
        company = bot._acting_company()
        in_company = bot.with_context(allowed_company_ids=company.ids)
        if bot.env["res.partner"].has_access("print_statement"):
            return in_company
        if company.id in bot.env.user._get_company_ids():
            return in_company.with_privilege(
                "account_telegram.privilege_print_own_statement",
                reason="a Telegram contact prints their own account statement",
            )
        return in_bot_company(bot, bot)

    def _partners_with_statement_lines(self, bot, partner_domain):
        lines = self._statement_bot(bot).env["account.move.line"]
        groups = lines._read_group(
            self._statement_lines_domain(bot, partner_domain), groupby=["partner_id"]
        )
        return bot.env["res.partner"].browse([partner.id for (partner,) in groups])

    def _statement_lines_domain(self, bot, partner_domain):
        return Domain(
            [
                ("partner_id", "any", partner_domain),
                ("company_id", "=", bot._acting_company().id),
                ("display_type", "not in", ("line_section", "line_note")),
                ("account_id.account_type", "=", "asset_receivable"),
                ("move_id.state", "=", "posted"),
            ]
        )

    def _first_statement_date(self, bot, partner, date_to):
        domain = self._statement_lines_domain(bot, [("id", "=", partner.id)])
        domain &= Domain("date", "<=", date_to)
        [(first,)] = (
            self._statement_bot(bot)
            .env["account.move.line"]
            ._read_group(domain, aggregates=["date:min"])
        )
        return first or None

    def _search_partners_for_ecmanager(self, bot, chat, search_term) -> None:
        tr_env = translation_env(bot, chat)

        if not self._check_reads_any_customer(bot, chat):
            return

        if len(search_term) < 2:
            bot.send_message(
                chat.chat_id,
                tr_env._("Please enter at least 2 characters to search."),
            )
            return

        self._offer_customers(
            bot,
            chat,
            search_term,
            self._partners_with_statement_lines(bot, [("name", "ilike", search_term)]),
        )

    def _offer_customers(
        self, bot, chat, search_term, partners_with_transactions
    ) -> None:
        tr_env = translation_env(bot, chat)

        if not partners_with_transactions:
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "No customers with transactions matched '<b>{search}</b>'.\n\n"
                    "Try another search term, or type /cancelar to exit."
                ).format(search=tg.escape(search_term)),
            )
            return

        self._flow_start(chat, "ecmanager_search", {"step": "search_partner"})

        bot.send_message(
            chat.chat_id,
            tr_env._(
                "📋 <b>Results for '{search}':</b>\n\nChoose the customer whose "
                "account statement to generate:"
            ).format(search=tg.escape(search_term)),
            reply_markup=kb.record_list(
                partners_with_transactions,
                lambda partner: partner.name,
                lambda partner: f"{CALLBACK_ECMANAGER}{partner.id}",
                limit=8,
                width=33,
            ),
        )

    def _handle_ecmanager_partner_selected(self, bot, chat, callback_data) -> None:
        tr_env = translation_env(bot, chat)

        if not self._check_reads_any_customer(bot, chat):
            return

        try:
            partner_id = int(callback_data.replace(CALLBACK_ECMANAGER, ""))
        except ValueError:
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "Error processing the selection. Please try again with /edocliente"
                ),
            )
            return

        target_partner = bot.env["res.partner"].browse(partner_id)
        if not target_partner.exists():
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "The selected customer no longer exists. Please try again with "
                    "/edocliente"
                ),
            )
            return

        if not self._has_partner_access(
            bot, chat, target_partner, target_name=target_partner.name
        ):
            return

        self._flow_start(chat, "ecmanager_period", {"target_partner_id": partner_id})

        keyboard = self._period_keyboard(
            tr_env, CALLBACK_ECM_PERIOD, CALLBACK_ECM_CUSTOM
        )

        bot.send_message(
            chat.chat_id,
            tr_env._(
                "✅ Selected customer: <b>{partner_name}</b>\n\n📅 Choose the period "
                "for the account statement:"
            ).format(partner_name=tg.escape(target_partner.name))
            + self._answer_hint(bot, chat),
            reply_markup=keyboard,
        )

    def _handle_ecmanager_period_selected(self, bot, chat, callback_data) -> None:
        tr_env = translation_env(bot, chat)

        if not self._check_reads_any_customer(bot, chat):
            return

        target_partner_id = self._flow_data(chat).get("target_partner_id")

        if not target_partner_id:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "The session has expired. Please use /edocliente to start again."
                ),
            )
            return

        target_partner = bot.env["res.partner"].browse(target_partner_id)
        if not target_partner.exists():
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "The selected customer no longer exists. Please try again with "
                    "/edocliente"
                ),
            )
            return

        if callback_data == CALLBACK_ECM_CUSTOM:
            self._flow_start(
                chat,
                "ecmanager_custom",
                {"step": "date_from", "target_partner_id": target_partner_id},
            )
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "📅 <b>Custom period for {partner_name}</b>\n\nEnter the <b>start "
                    "date</b> in YYYY-MM-DD format\nExample: <code>2024-01-01</code>"
                ).format(partner_name=tg.escape(target_partner.name))
                + self._answer_hint(bot, chat),
            )
            return

        period = callback_data.replace(CALLBACK_ECM_PERIOD, "")
        today = self._requester_today(chat)
        date_from, date_to = self._get_period_dates(period, today)

        if not date_from or not date_to:
            bot.send_message(
                chat.chat_id,
                tr_env._("Error computing the period. Please try again."),
            )
            return

        self._flow_end(chat)

        try:
            self._generate_and_send_report(
                bot,
                chat,
                target_partner,
                date_from,
                date_to,
                requester_partner=chat.partner_id,
            )
        except Exception:
            _logger.exception(
                "Error generating partner ledger for partner %s via ecmanager",
                target_partner_id,
            )
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "An error occurred while generating the account statement. Please "
                    "try again later."
                ),
            )

    def _has_partner_access(self, bot, chat, partner, target_name=None) -> bool:
        tr_env = translation_env(bot, chat)

        if not partner:
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "Your Telegram account is not connected to Odoo. In Odoo, open My "
                    "Preferences and press Connect Telegram, or ask an administrator for "
                    "an invitation."
                ),
            )
            return False

        if not self._partners_with_statement_lines(bot, [("id", "=", partner.id)]):
            if target_name:
                msg = tr_env._(
                    "No receivable transactions were found for customer <b>{name}</b>."
                ).format(name=tg.escape(target_name))
            else:
                msg = tr_env._(
                    "No receivable transactions were found for your account."
                )
            bot.send_message(chat.chat_id, msg)
            return False

        return True

    def _generate_and_send_report(
        self, bot, chat, partner, date_from, date_to, requester_partner=None
    ) -> None:
        tr_env = translation_env(bot, chat)
        if requester_partner is None:
            requester_partner = partner

        bot.send_message(
            chat.chat_id,
            tr_env._(
                "Generating the account statement for the period {date_from} to "
                "{date_to}...\nPlease wait a moment."
            ).format(date_from=tg.escape(date_from), date_to=tg.escape(date_to)),
        )

        try:
            with bot.env.cr.savepoint():
                company = bot._acting_company()
                report = self._statement_bot(bot).env.ref(
                    "account.partner_ledger_report"
                )
                options = report.get_options(
                    previous_options={
                        "forced_companies": [company.id],
                        "partner_ids": [partner.id],
                        "account_type": RECEIVABLE_ACCOUNT_TYPES,
                        "date": {"date_from": date_from, "date_to": date_to},
                        "export_mode": "print",
                        "unfold_all": True,
                    }
                )
                if options.get("partner_ids") != [partner.id] or [
                    option["id"] for option in options["companies"]
                ] != [company.id]:
                    raise UserError(
                        tr_env._(
                            "The statement could not be limited to this customer "
                            "in the bot's company"
                        )
                    )

                pdf_result = report.export_to_pdf(options)

                if not pdf_result or "file_content" not in pdf_result:
                    raise UserError(tr_env._("The PDF file could not be generated"))

                safe_name = re.sub(r'[\\/*?:"<>|]', "", partner.name).replace(" ", "_")
                file_name = f"Estado_Cuenta_{safe_name}_{date_from}_al_{date_to}.pdf"

                pdf_content_b64 = pdf_result["file_content"]
                if isinstance(pdf_content_b64, str):
                    file_content = base64.b64decode(pdf_content_b64)
                else:
                    file_content = pdf_content_b64

                if not file_content.startswith(b"%PDF"):
                    _logger.error(
                        "Generated content is not a valid PDF. First 20 bytes: %s",
                        file_content[:20],
                    )
                    raise UserError(
                        tr_env._("The generated content is not a valid PDF")
                    )

                bot.send_document(
                    chat.chat_id,
                    file_content,
                    file_name,
                    caption=tr_env._(
                        "Account statement for <b>{partner_name}</b>\nPeriod: {date_from} "
                        "to {date_to}"
                    ).format(
                        partner_name=tg.escape(partner.name),
                        date_from=tg.escape(date_from),
                        date_to=tg.escape(date_to),
                    ),
                )
        except Exception:
            self._create_report_log(
                bot, chat, requester_partner, partner, date_from, date_to, success=False
            )
            _logger.exception("Error in report generation")
            raise

        self._create_report_log(
            bot, chat, requester_partner, partner, date_from, date_to, success=True
        )

        _logger.info(
            "Partner Ledger report sent successfully to partner %s via Telegram",
            partner.id,
        )

    def _create_report_log(
        self,
        bot,
        chat,
        requester_partner,
        target_partner,
        date_from,
        date_to,
        success=True,
    ) -> None:
        try:
            with bot.env.cr.savepoint():
                bot.env["telegram.financial.report.log"].create(
                    {
                        "chat_id": chat.id,
                        "telegram_chat_id": chat.chat_id,
                        "requester_partner_id": (
                            requester_partner.id if requester_partner else False
                        ),
                        "target_partner_id": target_partner.id,
                        "requester_role": "manager"
                        if self._is_manager(chat)
                        else "user",
                        "date_from": date_from,
                        "date_to": date_to,
                        "success": success,
                    }
                )
        except Exception:
            _logger.exception("Failed to create financial report log")

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        tr_env = translation_env(bot, chat)
        offered = {
            command
            for command in self._telegram_commands()
            if self._offers_command(bot, chat, command, partner, internal_user)
        }
        estadocuenta_cmds = []
        if CMD_PERIOD_STATEMENT in offered:
            estadocuenta_cmds.append(
                tr_env._(
                    "/estadocuentaperiodo - Get your account statement for the "
                    "period you choose."
                )
            )
        if CMD_CUSTOMER_STATEMENT in offered:
            estadocuenta_cmds.append(
                tr_env._("/edocliente - Look up a customer's account statement.")
            )
        if not estadocuenta_cmds:
            return []
        return [(tr_env._("Financial Commands"), estadocuenta_cmds)]

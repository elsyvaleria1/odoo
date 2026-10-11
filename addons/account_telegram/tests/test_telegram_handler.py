import json
from datetime import date, datetime
from unittest.mock import patch

import psycopg
from freezegun import freeze_time

from odoo.libs.json import loads as json_loads

from ..models.telegram_handler import (
    CALLBACK_CUSTOM,
    CALLBACK_ECMANAGER,
)
from .common import PartnerLedgerTelegramTestCase
from odoo.addons.telegram.models.telegram_bot import TelegramBot

TODAY = date(2026, 9, 28)


class TestHandlerDeclarations(PartnerLedgerTelegramTestCase):
    def test_commands_are_partner_commands(self):
        commands = self.env["telegram.handler.account"]._telegram_commands()

        self.assertEqual(
            {name: spec.tier for name, spec in commands.items()},
            {
                "/estadocuentaperiodo": "partner",
                "/edocliente": "partner",
            },
        )

    def test_the_router_routes_the_commands_here(self):
        router = self.env["telegram.router"]
        for command in ("/estadocuentaperiodo", "/edocliente"):
            handler, _spec = router._command_owner(self.test_bot, command)
            self.assertEqual(handler._name, "telegram.handler.account")

    def test_buttons_already_sent_keep_their_prefixes(self):
        self.assertLessEqual(
            {"fin_period_", "fin_custom", "ecm_partner_", "ecm_period_", "ecm_custom"},
            set(self.env["telegram.handler.account"]._telegram_callback_prefixes()),
        )

    def test_the_renamed_commands_keep_their_xml_ids(self):
        self.assertEqual(
            self.env.ref("account_telegram.command_ecmanager").name, "/edocliente"
        )

    def test_the_own_statement_is_the_period_command_s_current_year(self):
        self.assertFalse(
            self.env["telegram.command"].search([("name", "=", "/estadoctapropio")])
        )
        self.assertFalse(
            self.env.ref(
                "account_telegram.command_estadocuenta", raise_if_not_found=False
            )
        )


class TestCalculatePeriodDates(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_calculate_period_1m(self):
        date_from, date_to = self.handler._get_period_dates("1m", TODAY)

        self.assertIsNotNone(date_from)
        self.assertIsNotNone(date_to)
        datetime.strptime(date_from, "%Y-%m-%d")
        datetime.strptime(date_to, "%Y-%m-%d")

    def test_calculate_period_3m(self):
        date_from, date_to = self.handler._get_period_dates("3m", TODAY)

        self.assertIsNotNone(date_from)
        self.assertIsNotNone(date_to)
        from_date = datetime.strptime(date_from, "%Y-%m-%d")
        to_date = datetime.strptime(date_to, "%Y-%m-%d")
        diff_months = (to_date.year - from_date.year) * 12 + (
            to_date.month - from_date.month
        )
        self.assertGreaterEqual(diff_months, 2)
        self.assertLessEqual(diff_months, 4)

    def test_calculate_period_6m(self):
        date_from, date_to = self.handler._get_period_dates("6m", TODAY)

        self.assertIsNotNone(date_from)
        self.assertIsNotNone(date_to)
        from_date = datetime.strptime(date_from, "%Y-%m-%d")
        to_date = datetime.strptime(date_to, "%Y-%m-%d")
        diff_months = (to_date.year - from_date.year) * 12 + (
            to_date.month - from_date.month
        )
        self.assertGreaterEqual(diff_months, 5)
        self.assertLessEqual(diff_months, 7)

    def test_calculate_period_current_year(self):
        self.assertEqual(
            self.handler._get_period_dates("year", TODAY), ("2026-01-01", "2026-12-31")
        )

    def test_calculate_period_1y(self):
        date_from, date_to = self.handler._get_period_dates("1y", TODAY)

        self.assertIsNotNone(date_from)
        self.assertIsNotNone(date_to)
        self.assertEqual(date_from, "2025-01-01")
        self.assertEqual(date_to, "2025-12-31")

    def test_calculate_period_invalid(self):
        date_from, date_to = self.handler._get_period_dates("invalid", TODAY)

        self.assertIsNone(date_from)
        self.assertIsNone(date_to)


class TestValidateDateFormat(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_valid_date_format(self):
        self.assertTrue(self.handler._is_date_format_valid("2024-01-15"))
        self.assertTrue(self.handler._is_date_format_valid("2023-12-31"))

    def test_invalid_date_format(self):
        self.assertFalse(self.handler._is_date_format_valid("01-15-2024"))
        self.assertFalse(self.handler._is_date_format_valid("2024/01/15"))
        self.assertFalse(self.handler._is_date_format_valid("invalid"))
        self.assertFalse(self.handler._is_date_format_valid(""))

    def test_unpadded_date_is_refused(self):
        self.assertFalse(self.handler._is_date_format_valid("2024-1-5"))
        self.assertFalse(self.handler._is_date_format_valid("2024-01-5"))

    def test_invalid_date_values(self):
        self.assertFalse(self.handler._is_date_format_valid("2024-13-01"))
        self.assertFalse(self.handler._is_date_format_valid("2024-02-30"))


class TestEstadoCuentaPeriodoCommand(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_estadocuentaperiodo_shows_keyboard(self):
        with self.mock_api_gateway_post() as mock_post:
            with patch.object(
                type(self.handler), "_has_partner_access", return_value=True
            ):
                self.handler._handle_estadocuentaperiodo_command(
                    self.test_bot,
                    self.test_chat,
                    args=[],
                    partner=self.test_partner,
                    internal_user=False,
                )

            mock_post.assert_called()
            payload = mock_post.call_args.kwargs.get("json", {})

            self.assertIn("reply_markup", payload)
            reply_markup = payload["reply_markup"]
            if isinstance(reply_markup, str):
                reply_markup = json_loads(reply_markup)
            self.assertIn("inline_keyboard", reply_markup)

    def test_estadocuentaperiodo_keyboard_has_all_options(self):
        with self.mock_api_gateway_post() as mock_post:
            with patch.object(
                type(self.handler), "_has_partner_access", return_value=True
            ):
                self.handler._handle_estadocuentaperiodo_command(
                    self.test_bot,
                    self.test_chat,
                    args=[],
                    partner=self.test_partner,
                    internal_user=False,
                )

            payload = mock_post.call_args.kwargs.get("json", {})
            reply_markup = payload["reply_markup"]
            if isinstance(reply_markup, str):
                reply_markup = json_loads(reply_markup)

            keyboard = reply_markup["inline_keyboard"]
            all_callbacks = []
            all_callbacks.extend(
                button.get("callback_data", "") for row in keyboard for button in row
            )

            self.assertEqual(all_callbacks[0], "fin_period_year")
            self.assertIn("fin_period_1m", all_callbacks)
            self.assertIn("fin_period_3m", all_callbacks)
            self.assertIn("fin_period_6m", all_callbacks)
            self.assertIn("fin_period_1y", all_callbacks)
            self.assertIn("fin_custom", all_callbacks)


class TestCallbackQueryHandling(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_callback_predefined_period(self):
        callback_query = self.mock_telegram_callback_query(
            callback_data="fin_period_1y"
        )

        with self.mock_api_gateway_post():
            with patch.object(
                type(self.handler), "_generate_and_send_report"
            ) as mock_report:
                self.handler._on_callback(
                    self.test_bot,
                    self.test_chat,
                    callback_query,
                    self.test_partner,
                    internal_user=False,
                )

                mock_report.assert_called_once()

    def test_callback_custom_period(self):
        callback_query = self.mock_telegram_callback_query(callback_data="fin_custom")

        with self.mock_api_gateway_post():
            with patch.object(
                type(self.handler), "_start_custom_period_flow"
            ) as mock_flow:
                self.handler._on_callback(
                    self.test_bot,
                    self.test_chat,
                    callback_query,
                    self.test_partner,
                    internal_user=False,
                )

                mock_flow.assert_called_once()

    def test_callback_unrelated_delegates_to_parent(self):
        callback_query = self.mock_telegram_callback_query(callback_data="other_action")

        self.assertIsNone(
            self.env["telegram.router"]._callback_owner(self.test_bot, "other_action")
        )
        with self.mock_api_gateway_post():
            handled = self.handler._on_callback(
                self.test_bot,
                self.test_chat,
                callback_query,
                self.test_partner,
                internal_user=False,
            )

        self.assertFalse(handled)


class TestCustomPeriodFlow(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_start_custom_flow_sets_state(self):
        with self.mock_api_gateway_post():
            self.handler._start_custom_period_flow(self.test_bot, self.test_chat)

        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.account")
        self.assertEqual(self.test_chat.flow_step, "estadocuenta_custom")
        self.assertEqual(self.test_chat.flow_data.get("step"), "date_from")

    def test_custom_flow_date_from_valid(self):
        self.test_chat._flow_start(
            "telegram.handler.account", "estadocuenta_custom", {"step": "date_from"}
        )

        message = {"text": "2024-01-01"}

        with self.mock_api_gateway_post():
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                internal_user=False,
            )

        self.assertEqual(self.test_chat.flow_data.get("step"), "date_to")
        self.assertEqual(self.test_chat.flow_data.get("date_from"), "2024-01-01")

    def test_custom_flow_date_from_invalid(self):
        self.test_chat._flow_start(
            "telegram.handler.account", "estadocuenta_custom", {"step": "date_from"}
        )

        message = {"text": "invalid-date"}

        with self.mock_api_gateway_post():
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                internal_user=False,
            )

        self.assertEqual(self.test_chat.flow_data.get("step"), "date_from")

    def test_custom_flow_date_to_generates_report(self):
        self.test_chat._flow_start(
            "telegram.handler.account",
            "estadocuenta_custom",
            {"step": "date_to", "date_from": "2024-01-01"},
        )

        message = {"text": "2024-12-31"}

        with self.mock_api_gateway_post():
            with patch.object(
                type(self.handler), "_generate_and_send_report"
            ) as mock_report:
                self.handler._on_message(
                    self.test_bot,
                    self.test_chat,
                    message,
                    self.test_partner,
                    internal_user=False,
                )

                mock_report.assert_called_once()

    def test_custom_flow_date_range_inverted(self):
        self.test_chat._flow_start(
            "telegram.handler.account",
            "estadocuenta_custom",
            {"step": "date_to", "date_from": "2024-12-31"},
        )

        message = {"text": "2024-01-01"}

        with self.mock_api_gateway_post() as mock_post:
            self.handler._on_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                internal_user=False,
            )

            payload = mock_post.call_args.kwargs.get("json", {})
            self.assertIn("must be later than", payload.get("text", ""))


class TestHelpSections(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_help_sections_for_partner(self):
        sections = self.handler._get_help_sections(
            self.test_bot,
            self.test_partner,
            internal_user=False,
        )

        financial_section = None
        for title, commands in sections:
            if "Financial" in title:
                financial_section = commands
                break

        self.assertIsNotNone(financial_section)
        section_text = " ".join(financial_section)
        self.assertNotIn("/estadoctapropio", section_text)
        self.assertIn("/estadocuentaperiodo", section_text)

    def test_help_sections_without_partner(self):
        sections = self.handler._get_help_sections(
            self.test_bot,
            partner=False,
            internal_user=False,
        )

        for title, _ in sections:
            if "Financial" in title:
                self.fail("Financial section should not appear for non-partners")


class TestValidatePartnerAccess(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_validate_partner_no_transactions(self):
        with self.mock_api_gateway_post() as mock_post:
            result = self.handler._has_partner_access(
                self.test_bot,
                self.test_chat,
                self.test_partner,
            )

        self.assertFalse(result)
        mock_post.assert_called()

    def test_lines_in_the_bot_company_count(self):
        self._post_statement_line(self.test_partner)
        with self.mock_api_gateway_post():
            result = self.handler._has_partner_access(
                self.test_bot, self.test_chat, self.test_partner
            )
        self.assertTrue(result)

    def test_lines_only_in_another_company_do_not_count(self):
        self._post_statement_line(self.test_partner)
        self.test_bot.company_id = self.env["res.company"].create(
            {"name": "Zyx Statement Company"}
        )
        with self.mock_api_gateway_post():
            result = self.handler._has_partner_access(
                self.test_bot, self.test_chat, self.test_partner
            )
        self.assertFalse(result)


class TestLedgerFlowGuard(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_ecmanager_is_registered_as_flow_starting(self):
        commands = self.handler._telegram_commands()
        self.assertTrue(commands["/edocliente"].starts_flow)
        self.assertFalse(commands["/estadocuentaperiodo"].starts_flow)

    def test_fin_custom_refused_while_another_flow_runs(self):
        self.test_chat._flow_start("telegram.handler.base", "other_module_intake")

        with self.mock_api_gateway_post():
            with patch.object(TelegramBot, "send_message") as mock_send:
                self.handler._on_callback(
                    self.test_bot,
                    self.test_chat,
                    self.mock_telegram_callback_query(callback_data=CALLBACK_CUSTOM),
                    self.test_partner,
                    internal_user=False,
                )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.base")
        self.assertIn("in progress", mock_send.call_args.args[1])

    def test_fin_custom_allowed_on_an_idle_chat(self):
        self.test_chat._flow_end()

        with self.mock_api_gateway_post():
            self.handler._on_callback(
                self.test_bot,
                self.test_chat,
                self.mock_telegram_callback_query(callback_data=CALLBACK_CUSTOM),
                self.test_partner,
                internal_user=False,
            )

        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.account")
        self.assertEqual(self.test_chat.flow_step, "estadocuenta_custom")

    def test_fin_custom_replaces_our_own_flow(self):
        self.test_chat._flow_start(
            "telegram.handler.account", "estadocuenta_custom", {"step": "date_to"}
        )

        with self.mock_api_gateway_post():
            self.handler._on_callback(
                self.test_bot,
                self.test_chat,
                self.mock_telegram_callback_query(callback_data=CALLBACK_CUSTOM),
                self.test_partner,
                internal_user=False,
            )

        self.assertEqual(self.test_chat.flow_data.get("step"), "date_from")

    def test_ecmanager_flows_are_reported_to_other_modules(self):
        self.test_chat._flow_start("telegram.handler.account", "ecmanager_search")

        self.assertEqual(
            self.env["telegram.router"]._flow_owner(self.test_chat), self.handler
        )
        self.assertEqual(
            self.handler._telegram_flow_label(self.test_bot, self.test_chat),
            "an account statement request",
        )

    def test_owns_only_its_own_flows(self):
        for flow in (
            "estadocuenta_custom",
            "ecmanager_search",
            "ecmanager_period",
            "ecmanager_custom",
        ):
            self.test_chat._flow_start("telegram.handler.account", flow)
            self.assertTrue(self.handler._owns_flow(self.test_chat), flow)
        self.test_chat._flow_start("telegram.handler.base", "fill_task")
        self.assertFalse(self.handler._owns_flow(self.test_chat))

    def test_router_gives_the_custom_period_text_to_its_flow(self):
        self.test_chat._flow_start(
            "telegram.handler.account", "estadocuenta_custom", {"step": "date_from"}
        )

        with self.mock_api_gateway_post():
            self.env["telegram.router"]._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                {"text": "2024-01-01"},
                self.test_partner,
                False,
            )

        self.assertEqual(self.test_chat.flow_data.get("step"), "date_to")
        self.assertEqual(self.test_chat.flow_data.get("date_from"), "2024-01-01")

    def test_router_refuses_fin_custom_during_another_flow(self):
        self.test_chat._flow_start("telegram.handler.base", "other_module_intake")

        with (
            self.mock_api_gateway_post(),
            patch.object(TelegramBot, "send_message") as mock_send,
        ):
            self.env["telegram.router"]._dispatch_callback_query(
                self.test_bot,
                self.mock_telegram_callback_query(callback_data=CALLBACK_CUSTOM),
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.base")
        self.assertIn("in progress", mock_send.call_args.args[1])


class TestReportLogAudit(PartnerLedgerTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_report_log_is_created(self):
        log_model = self.env["telegram.financial.report.log"]
        before = log_model.search_count([])
        self.handler._create_report_log(
            self.test_bot,
            self.test_chat,
            self.test_partner,
            self.test_partner,
            "2026-01-01",
            "2026-01-31",
        )
        self.assertEqual(log_model.search_count([]) - before, 1)


class TestManagerRole(PartnerLedgerTelegramTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]
        cls.test_user.group_ids = cls.env.ref("base.group_user")

    def _help_text(self):
        sections = self.handler._get_help_sections(
            self.test_bot, self.test_partner, self.test_user, chat=self.test_chat
        )
        return json.dumps(sections, default=str)

    def test_a_plain_internal_user_does_not_manage(self):
        self.assertFalse(self.handler._is_manager(self.test_chat))
        self.assertFalse(self.handler._is_manager(self.unlinked_chat))

    def test_an_accounting_manager_manages(self):
        self.test_user.group_ids |= self.env.ref("account.group_account_manager")
        self.assertTrue(self.handler._is_manager(self.test_chat))


class TestCustomerReach(PartnerLedgerTelegramTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]
        cls.test_user.group_ids = cls.env.ref("base.group_user")
        cls.customer = cls._create_partner({"name": "Zyxcliente SA"})
        cls.customer_chat = cls.env["telegram.chat"].create(
            {
                "chat_id": "24680",
                "chat_type": "private",
                "bot_id": cls.test_bot.id,
                "partner_id": cls.customer.id,
            }
        )

    def _help_text(self, partner, chat):
        sections = self.handler._get_help_sections(
            self.test_bot, partner, False, chat=chat
        )
        return json.dumps(sections, default=str)

    def _dispatch_ecmanager(self, chat, partner):
        with self.mock_api_gateway_post() as mock_post:
            self.env["telegram.router"]._dispatch_command(
                self.test_bot, chat, "/edocliente", [], partner, False
            )
        return json.dumps(mock_post.call_args_list, default=str)

    def test_an_accounting_reader_reads_any_customer(self):
        self.test_user.group_ids |= self.env.ref("account.group_account_readonly")
        self.assertTrue(self.handler._reads_any_customer(self.test_chat))
        self.assertIn("/edocliente", self._help_text(self.test_partner, self.test_chat))
        self._dispatch_ecmanager(self.test_chat, self.test_partner)
        self.assertEqual(self.test_chat.flow_step, "ecmanager_search")

    def test_a_plain_employee_reads_only_their_own(self):
        self.assertFalse(self.handler._reads_any_customer(self.test_chat))
        self.assertNotIn(
            "/edocliente", self._help_text(self.test_partner, self.test_chat)
        )
        sent = self._dispatch_ecmanager(self.test_chat, self.test_partner)
        self.assertIn("reads customer statements in Odoo", sent)
        self.assertFalse(self.test_chat.flow_step)

    def test_a_linked_customer_reads_only_their_own(self):
        self.assertFalse(self.handler._reads_any_customer(self.customer_chat))
        self.assertFalse(self.handler._reads_any_customer(self.unlinked_chat))
        self.assertNotIn(
            "/edocliente", self._help_text(self.customer, self.customer_chat)
        )
        sent = self._dispatch_ecmanager(self.customer_chat, self.customer)
        self.assertIn("linked Odoo user", sent)
        self.assertNotEqual(self.customer_chat.flow_step, "ecmanager_search")


class TestValuesArriveAsText(PartnerLedgerTelegramTestCase):
    NAME = "Ana_<Bold>*&co"
    ESCAPED = "Ana_&lt;Bold&gt;*&amp;co"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]
        cls.test_user.group_ids = cls.env.ref("account.group_account_readonly")
        cls.customer = cls._create_partner({"name": cls.NAME})

    def _sent(self, call):
        with self.mock_api_gateway_post() as mock_post:
            call()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["parse_mode"], "HTML")
        return payload["text"]

    def test_the_selected_customer_name_is_escaped(self):
        self._post_statement_line(self.customer)
        text = self._sent(
            lambda: self.handler._handle_ecmanager_partner_selected(
                self.test_bot, self.test_chat, f"{CALLBACK_ECMANAGER}{self.customer.id}"
            )
        )
        self.assertIn(f"<b>{self.ESCAPED}</b>", text)
        self.assertNotIn("<Bold>", text)

    def test_a_customer_without_lines_is_named_escaped(self):
        text = self._sent(
            lambda: self.handler._has_partner_access(
                self.test_bot,
                self.test_chat,
                self.customer,
                target_name=self.customer.name,
            )
        )
        self.assertIn(f"<b>{self.ESCAPED}</b>", text)

    def test_the_search_term_is_escaped(self):
        text = self._sent(
            lambda: self.handler._search_partners_for_ecmanager(
                self.test_bot, self.test_chat, "Zyx_<i>nobody"
            )
        )
        self.assertIn("<b>Zyx_&lt;i&gt;nobody</b>", text)


class TestRequesterClock(PartnerLedgerTelegramTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_last_month_on_the_evening_of_the_last_day(self):
        self.test_partner.tz = "America/Mexico_City"
        callback_query = self.mock_telegram_callback_query(
            callback_data="fin_period_1m"
        )
        with (
            freeze_time("2026-10-01 02:00:00"),
            self.mock_api_gateway_post(),
            patch.object(type(self.handler), "_generate_and_send_report") as report,
        ):
            self.handler._on_callback(
                self.test_bot,
                self.test_chat,
                callback_query,
                self.test_partner,
                internal_user=False,
            )
        self.assertEqual(report.call_args[0][3:5], ("2026-08-01", "2026-08-31"))

    def test_current_year_on_new_years_eve(self):
        self.test_partner.tz = "America/Mexico_City"
        callback_query = self.mock_telegram_callback_query(
            callback_data="fin_period_year"
        )
        with (
            freeze_time("2027-01-01 03:00:00"),
            self.mock_api_gateway_post(),
            patch.object(type(self.handler), "_generate_and_send_report") as report,
        ):
            self.handler._on_callback(
                self.test_bot,
                self.test_chat,
                callback_query,
                self.test_partner,
                internal_user=False,
            )
        self.assertEqual(report.call_args[0][3:5], ("2026-01-01", "2026-12-31"))

    def test_requester_timezone_wins_over_mexico_city(self):
        self.test_partner.tz = "America/Hermosillo"
        with freeze_time("2026-09-28 06:30:00"):
            today = self.handler._requester_today(self.test_chat)
        self.assertEqual(today, date(2026, 9, 27))

    def test_requester_without_timezone_is_on_mexico_city_time(self):
        self.test_partner.tz = False
        self.env.company.partner_id.tz = False
        with freeze_time("2026-09-28 02:00:00"):
            today = self.handler._requester_today(self.test_chat)
        self.assertEqual(today, date(2026, 9, 27))


class TestStatementPartnerSearch(PartnerLedgerTelegramTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def _ecmanager_offers(self, search_term):
        with (
            patch.object(type(self.handler), "_reads_any_customer", return_value=True),
            patch.object(TelegramBot, "send_message") as sent,
        ):
            self.handler._search_partners_for_ecmanager(
                self.test_bot, self.test_chat, search_term
            )
        markup = sent.call_args.kwargs.get("reply_markup") or {}
        return {
            int(button["callback_data"].removeprefix(CALLBACK_ECMANAGER))
            for row in markup.get("inline_keyboard", [])
            for button in row
        }

    def test_customers_after_the_first_ten_names_are_offered(self):
        partners = self.env["res.partner"]
        for index in range(1, 13):
            partners |= self._create_partner(
                {"name": f"Zyxlopez {index:02d}", "is_company": True}
            )
        self._post_statement_line(partners[10])
        self._post_statement_line(partners[11])
        self.assertEqual(self._ecmanager_offers("zyxlopez"), set(partners[10:].ids))

    def test_individual_customers_are_offered(self):
        person = self._create_partner({"name": "Zyxana Casillas", "is_company": False})
        self._post_statement_line(person)
        self.assertEqual(self._ecmanager_offers("zyxana"), {person.id})

    def test_customer_with_lines_only_in_another_company_is_not_offered(self):
        customer = self._create_partner({"name": "Zyxotra SA", "is_company": True})
        self._post_statement_line(customer)
        self.test_bot.company_id = self.env["res.company"].create(
            {"name": "Zyx Statement Company"}
        )
        self.assertEqual(self._ecmanager_offers("zyxotra"), set())


class TestReceivableOnly(PartnerLedgerTelegramTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.handler = cls.env["telegram.handler.account"]

    def test_a_supplier_without_receivables_has_no_statement(self):
        supplier = self._create_partner({"name": "Zyxproveedor SA"})
        self._post_statement_line(supplier, account_type="liability_payable")
        self.assertFalse(
            self.handler._partners_with_statement_lines(
                self.test_bot, [("id", "=", supplier.id)]
            )
        )

    def test_the_report_is_asked_for_receivable_accounts_only(self):
        report_class = type(self.env["report.formula"])
        printed = []

        def fake_pdf(report, options):
            printed.append(options)
            return {"file_content": b"%PDF-1.4 statement"}

        with (
            patch.object(
                report_class, "export_to_pdf", autospec=True, side_effect=fake_pdf
            ),
            patch.object(TelegramBot, "send_message"),
            patch.object(TelegramBot, "send_document"),
        ):
            self.handler._generate_and_send_report(
                self.test_bot,
                self.test_chat,
                self.test_partner,
                "2026-01-01",
                "2026-09-28",
            )
        selected = {
            choice["id"] for choice in printed[0]["account_type"] if choice["selected"]
        }
        self.assertEqual(selected, {"trade_receivable", "non_trade_receivable"})


class TestReportFailure(PartnerLedgerTelegramTestCase):
    def test_a_database_error_in_the_report_is_logged_and_raised(self):
        handler = self.env["telegram.handler.account"]

        def statement_bot_hits_a_database_error(self, bot):
            self.env.cr.execute(
                "DO $$ BEGIN RAISE EXCEPTION 'disk full' USING ERRCODE = '53100'; "
                "END $$",
                log_exceptions=False,
            )

        Log = self.env["telegram.financial.report.log"]
        raised = None
        with (
            self.mock_api_gateway_post(),
            patch.object(
                type(handler),
                "_statement_bot",
                statement_bot_hits_a_database_error,
            ),
        ):
            try:
                handler._generate_and_send_report(
                    self.test_bot,
                    self.test_chat,
                    self.test_partner,
                    "2026-01-01",
                    "2026-01-31",
                )
            except psycopg.errors.DiskFull as exc:
                raised = exc

        self.assertIsNotNone(raised)
        self.assertFalse(self.env.cr.in_failed_transaction())
        self.assertEqual(
            Log.search([("target_partner_id", "=", self.test_partner.id)]).mapped(
                "success"
            ),
            [False],
        )

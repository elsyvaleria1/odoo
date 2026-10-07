from datetime import UTC
from unittest.mock import patch

from odoo import Command
from odoo.libs.datetime import timezone
from odoo.tools.date_utils import utcnow

from .common import AttendanceTelegramTestCase
from odoo.addons.telegram.models.telegram_bot import TelegramBot


class TestEmployeeValidation(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.attendance"]

    def test_the_menu_offers_attendance_to_employees_only(self):
        entrada = self.env["telegram.command"]._for_name("/entrada")
        self.test_bot.command_ids = [Command.link(entrada.id)]
        self.assertIn("entrada", [e["command"] for e in self.test_chat.command_menu])

        hand = self._create_partner({"name": "No Employee Hand"})
        account = self._bound_account("566011", hand)
        chat = self.env["telegram.chat"].create(
            {
                "chat_id": "566011",
                "chat_type": "private",
                "bot_id": self.test_bot.id,
                "account_id": account.id,
            }
        )
        self.assertNotIn("entrada", [e["command"] for e in chat._get_command_menu()])

    def test_unlinked_chat_denied_attendance_commands(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            result = self.handler._has_employee_access(
                self.test_bot,
                self.unlinked_chat,
                False,
            )

            self.assertFalse(result)
            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            self.assertIn("must be linked", payload.get("text", "").lower())

    def test_partner_without_employee_denied(self):
        partner_no_emp = self._create_partner({"name": "No Employee Partner"})

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            result = self.handler._has_employee_access(
                self.test_bot,
                self.test_chat,
                partner_no_emp,
            )

            self.assertFalse(result)
            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            self.assertIn("only employees", payload.get("text", "").lower())

    def test_employee_partner_allowed(self):
        result = self.handler._has_employee_access(
            self.test_bot,
            self.test_chat,
            self.test_partner,
        )

        self.assertTrue(result)


class TestTimeArgumentParsing(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.attendance"]

    def test_parse_valid_time_argument(self):
        dt, bad_time = self.handler._parse_time_argument(
            ["14:30"], "America/Mexico_City"
        )

        self.assertIsNone(bad_time)
        self.assertIsNotNone(dt)
        self.assertIsNone(dt.tzinfo)

    def test_parse_invalid_time_format_returns_the_offending_token(self):
        dt, bad_time = self.handler._parse_time_argument(
            ["invalid"], "America/Mexico_City"
        )

        self.assertIsNone(dt)
        self.assertEqual(bad_time, "invalid")

    def test_parse_no_argument_returns_current_time(self):
        dt, bad_time = self.handler._parse_time_argument([], "America/Mexico_City")

        self.assertIsNone(bad_time)
        self.assertIsNotNone(dt)
        now = utcnow()
        diff = abs((dt - now).total_seconds())
        self.assertLess(diff, 60)

    def test_parse_with_base_date(self):
        yesterday = self.yesterday_utc(hour=9, minute=0)

        dt, bad_time = self.handler._parse_time_argument(
            ["17:00"], "America/Mexico_City", base_date_utc=yesterday
        )

        self.assertIsNone(bad_time)
        self.assertIsNotNone(dt)
        tz = timezone("America/Mexico_City")
        dt_local = dt.replace(tzinfo=UTC).astimezone(tz)
        yesterday_local = yesterday.replace(tzinfo=UTC).astimezone(tz)
        self.assertEqual(dt_local.date(), yesterday_local.date())


class TestCheckInCommand(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.attendance"]

    def test_check_in_creates_attendance(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_check_in_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("check-in", text.lower())

        attendance = self.env["hr.attendance"].search(
            [
                ("employee_id", "=", self.test_employee.id),
                ("check_out", "=", False),
            ],
            limit=1,
        )
        self.assertTrue(attendance)

    def test_check_in_greets_a_name_as_literal_html_text(self):
        self.test_user.name = "Ana_<Bold>*&co"
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_check_in_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("Ana_&lt;Bold&gt;*&amp;co", payload["text"])
        self.assertNotIn("<Bold>", payload["text"])

    def test_a_bad_time_is_echoed_as_literal_html_text(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_check_in_command(
                self.test_bot,
                self.test_chat,
                ["<b>9"],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

        text = mock_post.call_args.kwargs["json"]["text"]
        self.assertIn("&lt;b&gt;9", text)
        self.assertNotIn("<b>9", text)

    def test_check_in_with_open_attendance_same_day_denied(self):
        self.create_attendance()

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_check_in_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("you already have", text.lower())

    def test_check_in_with_open_attendance_previous_day_starts_flow(self):
        yesterday = self.yesterday_utc(hour=9, minute=0)
        self.create_attendance(check_in=yesterday)

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_check_in_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("open check-in", text.lower())

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.attendance")
        self.assertEqual(self.test_chat.flow_step, "checkout_time")


class TestCheckOutCommand(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.attendance"]

    def test_check_out_closes_attendance(self):
        attendance = self.create_attendance()
        self.assertFalse(attendance.check_out)

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_check_out_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("check-out", text.lower())

        attendance.invalidate_recordset()
        self.assertTrue(attendance.check_out)

    def test_check_out_without_open_attendance_denied(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_check_out_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("no open check-in", text.lower())


class TestLunchOutCommand(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.attendance"]

    def test_lunch_out_records_time(self):
        attendance = self.create_attendance()
        self.assertFalse(attendance.lunch_out)

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_lunch_out_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("lunch break", text.lower())

        attendance.invalidate_recordset()
        self.assertTrue(attendance.lunch_out)

    def test_lunch_out_without_check_in_denied(self):
        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_lunch_out_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("active check-in", text.lower())

    def test_lunch_out_already_recorded_denied(self):
        self.create_attendance(
            check_in=self.get_utc_datetime(-4),
            lunch_out=self.get_utc_datetime(-1),
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_lunch_out_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("you already recorded", text.lower())


class TestLunchInCommand(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.attendance"]

    def test_lunch_in_records_time(self):
        attendance = self.create_attendance(
            check_in=self.get_utc_datetime(-4),
            lunch_out=self.get_utc_datetime(-1),
        )
        self.assertFalse(attendance.lunch_in)

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_lunch_in_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("return from lunch", text.lower())

        attendance.invalidate_recordset()
        self.assertTrue(attendance.lunch_in)
        self.assertGreater(attendance.lunch_hours, 0)

    def test_lunch_in_without_lunch_out_denied(self):
        self.create_attendance()

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_lunch_in_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("have not recorded", text.lower())

    def test_lunch_in_already_recorded_denied(self):
        self.create_attendance(
            check_in=self.get_utc_datetime(-4),
            lunch_out=self.get_utc_datetime(-2),
            lunch_in=self.get_utc_datetime(-1),
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.handler._handle_lunch_in_command(
                self.test_bot,
                self.test_chat,
                [],
                partner=self.test_partner,
                internal_user=self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("you already recorded", text.lower())


class TestConversationalCheckoutFlow(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.router = self.env["telegram.router"]
        self.test_bot.write(
            {
                "command_ids": [
                    Command.link(
                        self.env.ref("hr_attendance_telegram.command_entrada").id
                    )
                ]
            }
        )

    def test_checkout_time_response_closes_and_creates_new(self):
        yesterday = self.yesterday_utc(hour=9, minute=0)
        old_attendance = self.create_attendance(check_in=yesterday)

        pending_check_in = utcnow().replace(second=0, microsecond=0)
        self.env["telegram.handler.attendance"]._flow_start(
            self.test_chat,
            "checkout_time",
            {
                "pending_check_in": pending_check_in.isoformat(),
                "open_attendance_id": old_attendance.id,
            },
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text="17:00",
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("check-out", text.lower())
            self.assertIn("check-in", text.lower())

        old_attendance.invalidate_recordset()
        self.assertTrue(old_attendance.check_out)

        new_attendance = self.env["hr.attendance"].search(
            [
                ("employee_id", "=", self.test_employee.id),
                ("check_out", "=", False),
                ("id", "!=", old_attendance.id),
            ],
            limit=1,
        )
        self.assertTrue(new_attendance)

        self.test_chat.invalidate_recordset()
        self.assertFalse(self.test_chat.flow_owner)

    def test_invalid_checkout_time_keeps_the_flow(self):
        yesterday = self.yesterday_utc(hour=9, minute=0)
        old_attendance = self.create_attendance(check_in=yesterday)

        pending_check_in = utcnow().replace(second=0, microsecond=0)
        self.env["telegram.handler.attendance"]._flow_start(
            self.test_chat,
            "checkout_time",
            {
                "pending_check_in": pending_check_in.isoformat(),
                "open_attendance_id": old_attendance.id,
            },
        )

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        message = self.mock_telegram_message(
            chat_id=self.test_chat.chat_id,
            text="invalid time",
        )

        with self.mock_api_gateway_post(mock_response) as mock_post:
            self.router._dispatch_free_message(
                self.test_bot,
                self.test_chat,
                message,
                self.test_partner,
                self.test_user,
            )

            self.assertTrue(mock_post.called)
            payload = mock_post.call_args.kwargs.get("json", {})
            text = payload.get("text", "")
            self.assertIn("invalid", text.lower())

        old_attendance.invalidate_recordset()
        self.assertFalse(old_attendance.check_out)
        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_step, "checkout_time")


class TestHelpSections(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.attendance"]

    def test_help_includes_attendance_commands_for_employee(self):
        commands = ["/entrada", "/salida", "/comida", "/regresocomida"]
        for cmd in commands:
            command = self.env["telegram.command"]._for_name(cmd)
            self.test_bot.write({"command_ids": [(4, command.id)]})

        sections = self.handler._get_help_sections(
            self.test_bot,
            self.test_partner,
            self.test_user,
        )

        attendance_section = None
        for title, cmds in sections:
            if "Attendance" in title:
                attendance_section = cmds
                break

        self.assertIsNotNone(attendance_section)
        section_text = " ".join(attendance_section)
        self.assertIn("/entrada", section_text)
        self.assertIn("/salida", section_text)
        self.assertIn("/comida", section_text)
        self.assertIn("/regresocomida", section_text)

    def test_help_excludes_attendance_for_non_employee(self):
        partner_no_emp = self._create_partner({"name": "No Employee Partner"})

        sections = self.handler._get_help_sections(
            self.test_bot,
            partner_no_emp,
            False,
        )

        for title, _cmds in sections:
            self.assertNotIn("Attendance", title)


class TestCommandDispatch(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.attendance"]

    def test_attendance_commands_declared(self):
        commands = self.handler._telegram_commands()
        self.assertEqual(
            {command: spec.method for command, spec in commands.items()},
            {
                "/entrada": "_handle_check_in_command",
                "/salida": "_handle_check_out_command",
                "/comida": "_handle_lunch_out_command",
                "/regresocomida": "_handle_lunch_in_command",
            },
        )

    def test_attendance_commands_require_partner(self):
        for command, spec in self.handler._telegram_commands().items():
            self.assertEqual(spec.tier, "partner", command)

    def test_router_routes_attendance_commands_to_this_handler(self):
        for command in ("/entrada", "/salida", "/comida", "/regresocomida"):
            handler, _spec = self.env["telegram.router"]._command_owner(
                self.test_bot, command
            )
            self.assertEqual(handler._name, "telegram.handler.attendance")

    def test_checkout_flow_is_named_in_the_busy_notice(self):
        self.assertEqual(
            self.handler._telegram_flow_label(self.test_bot, self.test_chat),
            "an attendance record",
        )

    def test_dispatch_entrada_command(self):
        entrada_cmd = self.env["telegram.command"]._for_name("/entrada")
        self.test_bot.write({"command_ids": [(4, entrada_cmd.id)]})

        mock_response = self.mock_telegram_response(
            success=True, result={"message_id": 1}
        )

        with self.mock_api_gateway_post(mock_response):
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/entrada",
                [],
                self.test_partner,
                self.test_user,
            )

        attendance = self.env["hr.attendance"].search(
            [
                ("employee_id", "=", self.test_employee.id),
                ("check_out", "=", False),
            ],
            limit=1,
        )
        self.assertTrue(attendance)


class TestCheckInFlowGuard(AttendanceTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.handler = self.env["telegram.handler.attendance"]
        self.test_bot.write(
            {
                "command_ids": [
                    Command.link(
                        self.env.ref("hr_attendance_telegram.command_entrada").id
                    )
                ]
            }
        )

    def test_entrada_is_registered_as_flow_starting(self):
        commands = self.handler._telegram_commands()
        self.assertTrue(commands["/entrada"].starts_flow)
        for command in ("/salida", "/comida", "/regresocomida"):
            self.assertFalse(commands[command].starts_flow)

    def test_entrada_refused_while_another_flow_runs(self):
        self.test_chat._flow_start("telegram.handler.base", "other", {"step": 2})

        with patch.object(TelegramBot, "send_message") as mock_send:
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/entrada",
                [],
                self.test_partner,
                False,
            )

        self.test_chat.invalidate_recordset()
        self.assertEqual(self.test_chat.flow_owner, "telegram.handler.base")
        self.assertEqual(self.test_chat.flow_data, {"step": 2})
        self.assertIn("in progress", mock_send.call_args.args[1])

    def test_pending_checkout_blocks_other_flows(self):
        self.handler._flow_start(self.test_chat, "checkout_time")

        with patch.object(TelegramBot, "send_message") as mock_send:
            self.env["telegram.router"]._dispatch_command(
                self.test_bot,
                self.test_chat,
                "/entrada",
                [],
                self.test_partner,
                False,
            )

        self.assertIn("an attendance record", mock_send.call_args.args[1])

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfoNotFoundError

from odoo import models
from odoo.exceptions import ValidationError
from odoo.libs.datetime import timezone
from odoo.tools.translate import LazyTranslate

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools.authority import in_bot_company, keeping
from odoo.addons.telegram.tools.dispatch import (
    TelegramCommand,
    log_command_execution,
    translation_env,
)

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

DEFAULT_TZ = "America/Mexico_City"


class TelegramHandlerAttendance(models.AbstractModel):
    _name = "telegram.handler.attendance"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Attendance"

    def _telegram_commands(self) -> dict:
        return {
            "/entrada": TelegramCommand(
                "_handle_check_in_command",
                "partner",
                starts_flow=True,
                description=_lt("Record your arrival"),
                company="choose",
            ),
            "/salida": TelegramCommand(
                "_handle_check_out_command",
                "partner",
                description=_lt("Record your departure"),
                company="choose",
            ),
            "/comida": TelegramCommand(
                "_handle_lunch_out_command",
                "partner",
                description=_lt("Start your lunch break"),
                company="choose",
            ),
            "/regresocomida": TelegramCommand(
                "_handle_lunch_in_command",
                "partner",
                description=_lt("Come back from lunch"),
                company="choose",
            ),
        }

    def _command_allowed(self, bot, chat, command, partner, internal_user) -> bool:
        return bool(self._employee_companies(bot, partner))

    def _command_companies(self, bot, chat, command, partner, internal_user):
        return self._employee_companies(bot, partner)

    def _explain_command_refusal(
        self, bot, chat, command, partner, internal_user
    ) -> None:
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._("Only employees can use attendance commands."),
        )

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("an attendance record")

    @staticmethod
    def _own_attendance(bot, partner, model_name):
        return in_bot_company(
            partner.env[model_name]
            .with_acting_partner(partner)
            .with_privilege(
                "hr_attendance_telegram.privilege_record_own_attendance",
                reason="an employee records their own attendance from Telegram",
            ),
            bot,
        )

    def _employee(self, bot, partner):
        if not partner:
            return partner.env["hr.employee"]
        company = bot.with_env(partner.env)._acting_company()
        return self._own_attendance(bot, partner, "hr.employee").search(
            [("partner_id", "=", partner.id), ("company_id", "=", company.id)],
            limit=1,
        )

    def _employee_companies(self, bot, partner):
        served = keeping(bot).company_ids.with_env(bot.env)
        if not partner:
            return served.browse()
        return served.filtered(
            lambda company: self._employee(
                bot.with_context(telegram_company_id=company.id),
                partner.with_context(telegram_company_id=company.id),
            )
        )

    def _has_employee_access(self, bot, chat, partner) -> bool:
        if not partner:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Your chat must be linked to a contact to use attendance commands."
                ),
            )
            return False

        if not self._employee(bot, partner):
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Only employees can use attendance commands."
                ),
            )
            return False

        return True

    def _parse_time_argument(self, args, user_tz_str, base_date_utc=None) -> tuple:
        try:
            user_tz = timezone(user_tz_str)
        except ZoneInfoNotFoundError:
            user_tz = timezone(DEFAULT_TZ)

        now_user_tz = datetime.now(user_tz)
        if base_date_utc:
            base_dt_user_tz = base_date_utc.replace(tzinfo=UTC).astimezone(user_tz)
            target_dt_user_tz = base_dt_user_tz.replace(
                hour=now_user_tz.hour,
                minute=now_user_tz.minute,
                second=now_user_tz.second,
                microsecond=0,
            )
        else:
            target_dt_user_tz = now_user_tz.replace(microsecond=0)

        if args:
            time_str = args[0]
            try:
                time_parts = time_str.split(":")
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                target_dt_user_tz = target_dt_user_tz.replace(hour=hour, minute=minute)
            except ValueError, IndexError:
                return None, time_str

        return target_dt_user_tz.astimezone(UTC).replace(tzinfo=None), None

    def _notify_bad_time(self, bot, chat, bad_time) -> None:
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "The time format '%(value)s' is invalid. Please use HH:MM (e.g. 17:00)."
            )
            % {"value": tg.escape(bad_time)},
        )

    def _paused_workorders_notice(self, bot, chat, count):
        return translation_env(bot, chat)._(
            "\n\n%(count)s active work orders were paused automatically."
        ) % {"count": count}

    def _get_last_attendance(self, bot, partner):
        attendance = self._own_attendance(bot, partner, "hr.attendance")
        employee = self._employee(bot, partner)
        if not employee:
            return attendance
        return attendance.search(
            [
                ("employee_id", "=", employee.id),
                ("check_out", "=", False),
            ],
            limit=1,
            order="check_in desc",
        )

    def _get_active_workorders(self, employee):
        if not employee or not employee.user_id:
            return []

        productivities = employee.env["mrp.workcenter.productivity"].with_user(
            employee.user_id
        )
        if not productivities.has_access("read"):
            return []
        return productivities.search(
            [
                ("user_id", "=", employee.user_id.id),
                ("date_end", "=", False),
                ("loss_type", "in", ["productive", "performance"]),
            ]
        ).mapped("workorder_id")

    def _stop_employee_workorders(self, employee, reason="attendance_checkout"):
        active_workorders = self._get_active_workorders(employee)

        if not active_workorders:
            return 0

        stopped_count = 0
        for workorder in active_workorders:
            try:
                workorder.with_user(employee.user_id).end_previous(doall=False)
                stopped_count += 1
                _logger.info(
                    "Stopped workorder %s for employee %s due to %s",
                    workorder.name,
                    employee.name,
                    reason,
                )
            except Exception:
                _logger.exception(
                    "Error stopping workorder %s for employee %s",
                    workorder.name,
                    employee.name,
                )

        return stopped_count

    @log_command_execution
    def _handle_check_in_command(
        self,
        bot,
        chat,
        args,
        partner=False,
        internal_user=False,
    ) -> None:
        if not self._has_employee_access(bot, chat, partner):
            return

        user_tz_str = (internal_user and internal_user.tz) or DEFAULT_TZ
        check_in_time, bad_time = self._parse_time_argument(args, user_tz_str)
        if bad_time:
            self._notify_bad_time(bot, chat, bad_time)
            return

        latest_attendance = self._get_last_attendance(bot, partner)
        if latest_attendance.check_in:
            user_tz = timezone(user_tz_str)
            check_in_local = latest_attendance.check_in.replace(tzinfo=UTC).astimezone(
                user_tz
            )
            today_local = datetime.now(user_tz).date()

            if check_in_local.date() < today_local:
                self._flow_start(
                    chat,
                    "checkout_time",
                    {
                        "pending_check_in": check_in_time.isoformat(),
                        "open_attendance_id": latest_attendance.id,
                    },
                )
                bot.send_message(
                    chat.chat_id,
                    translation_env(bot, chat)._(
                        "You have an open check-in from %(date)s.\n"
                        "What time did you clock out that day? (HH:MM format)"
                    )
                    % {"date": check_in_local.strftime("%d/%m/%Y")},
                )
                return

            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "You already have a check-in today with no check-out."
                ),
            )
            return

        try:
            attendance = self._own_attendance(bot, partner, "hr.attendance")
            attendance.create(
                {
                    "employee_id": self._employee(bot, partner).id,
                    "check_in": check_in_time,
                }
            )
            formatted_time = (
                check_in_time.replace(tzinfo=UTC)
                .astimezone(timezone(user_tz_str))
                .strftime("%H:%M")
            )
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Hello %(name)s! Your check-in was recorded at %(time)s. "
                    "Have a great day!"
                )
                % {
                    "name": tg.escape(
                        internal_user.name if internal_user else partner.name
                    ),
                    "time": formatted_time,
                },
            )
        except ValidationError as e:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("Error: %(error)s")
                % {"error": tg.escape(e)},
            )

    @log_command_execution
    def _handle_check_out_command(
        self,
        bot,
        chat,
        args,
        partner=False,
        internal_user=False,
    ) -> None:
        if not self._has_employee_access(bot, chat, partner):
            return

        attendance = self._get_last_attendance(bot, partner)
        if not attendance.check_in:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "You have no open check-in to close with a check-out."
                ),
            )
            return
        user_tz_str = (internal_user and internal_user.tz) or DEFAULT_TZ
        check_out_time, bad_time = self._parse_time_argument(
            args, user_tz_str, base_date_utc=attendance.check_in
        )
        if bad_time:
            self._notify_bad_time(bot, chat, bad_time)
            return
        try:
            attendance.write({"check_out": check_out_time})

            employee = self._employee(bot, partner)
            stopped_workorders = self._stop_employee_workorders(employee, "check_out")

            formatted_time = (
                check_out_time.replace(tzinfo=UTC)
                .astimezone(timezone(user_tz_str))
                .strftime("%H:%M")
            )
            message = translation_env(bot, chat)._(
                "Your check-out was recorded at %(time)s. See you later, %(name)s!"
            ) % {
                "time": formatted_time,
                "name": tg.escape(
                    internal_user.name if internal_user else partner.name
                ),
            }
            if stopped_workorders > 0:
                message += self._paused_workorders_notice(bot, chat, stopped_workorders)

            bot.send_message(chat.chat_id, message)

        except ValidationError as e:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("Error: %(error)s")
                % {"error": tg.escape(e)},
            )

    @log_command_execution
    def _handle_lunch_out_command(
        self,
        bot,
        chat,
        args,
        partner=False,
        internal_user=False,
    ) -> None:
        if not self._has_employee_access(bot, chat, partner):
            return

        user_tz_str = (internal_user and internal_user.tz) or DEFAULT_TZ
        lunch_out_time, bad_time = self._parse_time_argument(args, user_tz_str)
        if bad_time:
            self._notify_bad_time(bot, chat, bad_time)
            return

        attendance = self._get_last_attendance(bot, partner)
        if not attendance.check_in:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "You need an active check-in to record a lunch break."
                ),
            )
            return

        if attendance.lunch_out:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("You already recorded your lunch break."),
            )
            return
        try:
            attendance.write({"lunch_out": lunch_out_time})

            employee = self._employee(bot, partner)
            stopped_workorders = self._stop_employee_workorders(employee, "lunch_out")

            formatted_time = (
                lunch_out_time.replace(tzinfo=UTC)
                .astimezone(timezone(user_tz_str))
                .strftime("%H:%M")
            )

            message = translation_env(bot, chat)._(
                "Your lunch break was recorded at %(time)s. Enjoy your meal!"
            ) % {"time": formatted_time}
            if stopped_workorders > 0:
                message += self._paused_workorders_notice(bot, chat, stopped_workorders)

            bot.send_message(chat.chat_id, message)
        except ValidationError as e:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("Error: %(error)s")
                % {"error": tg.escape(e)},
            )

    @log_command_execution
    def _handle_lunch_in_command(
        self,
        bot,
        chat,
        args,
        partner=False,
        internal_user=False,
    ) -> None:
        if not self._has_employee_access(bot, chat, partner):
            return

        user_tz_str = (internal_user and internal_user.tz) or DEFAULT_TZ
        lunch_in_time, bad_time = self._parse_time_argument(args, user_tz_str)
        if bad_time:
            self._notify_bad_time(bot, chat, bad_time)
            return

        attendance = self._get_last_attendance(bot, partner)
        if not attendance.check_in or not attendance.lunch_out:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "You have not recorded a lunch break, so you cannot record a return."
                ),
            )
            return

        if attendance.lunch_in:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "You already recorded your return from lunch."
                ),
            )
            return

        try:
            attendance.write({"lunch_in": lunch_in_time})
            formatted_time = (
                lunch_in_time.replace(tzinfo=UTC)
                .astimezone(timezone(user_tz_str))
                .strftime("%H:%M")
            )
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Your return from lunch was recorded at %(time)s."
                )
                % {"time": formatted_time},
            )
        except ValidationError as e:
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("Error: %(error)s")
                % {"error": tg.escape(e)},
            )

    def _on_message(self, bot, chat, message, partner, internal_user):
        if self._flow_step(chat) != "checkout_time":
            return False
        self._process_checkout_time_response(bot, chat, message, partner, internal_user)
        return True

    def _process_checkout_time_response(
        self, bot, chat, message, partner, internal_user
    ) -> None:
        user_tz_str = (internal_user and internal_user.tz) or DEFAULT_TZ
        time_text = message.get("text", "").strip()

        context = self._flow_data(chat)
        open_attendance_id = context.get("open_attendance_id")
        pending_check_in_str = context.get("pending_check_in")

        if not open_attendance_id or not pending_check_in_str:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "Something went wrong. Please try again with /entrada"
                ),
            )
            return

        attendance = self._own_attendance(bot, partner, "hr.attendance").browse(
            open_attendance_id
        )
        if (
            not attendance.exists()
            or attendance.check_out
            or attendance.employee_id != self._employee(bot, partner)
        ):
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "That attendance is already closed. Use /entrada to record a new one."
                ),
            )
            return

        check_out_time, bad_time = self._parse_time_argument(
            [time_text], user_tz_str, base_date_utc=attendance.check_in
        )
        if bad_time:
            self._notify_bad_time(bot, chat, bad_time)
            return

        try:
            attendance.write({"check_out": check_out_time})

            employee = self._employee(bot, partner)
            self._stop_employee_workorders(employee, "delayed_checkout")

            user_tz = timezone(user_tz_str)
            checkout_dt_local = check_out_time.replace(tzinfo=UTC).astimezone(user_tz)
            formatted_checkout = checkout_dt_local.strftime("%H:%M")
            checkout_date = checkout_dt_local.strftime("%d/%m/%Y")

            pending_check_in = datetime.fromisoformat(pending_check_in_str)
            self._own_attendance(bot, partner, "hr.attendance").create(
                {
                    "employee_id": employee.id,
                    "check_in": pending_check_in,
                }
            )

            formatted_checkin = (
                pending_check_in.replace(tzinfo=UTC)
                .astimezone(user_tz)
                .strftime("%H:%M")
            )
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "✅ Your check-out for %(date)s was recorded at %(out_time)s.\n\n"
                    "Hello %(name)s! Your check-in for today was recorded at "
                    "%(in_time)s. Have a great day!"
                )
                % {
                    "date": checkout_date,
                    "out_time": formatted_checkout,
                    "name": tg.escape(
                        internal_user.name if internal_user else partner.name
                    ),
                    "in_time": formatted_checkin,
                },
            )

        except ValidationError as e:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._("Error: %(error)s")
                % {"error": tg.escape(e)},
            )

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        tr_env = translation_env(bot, chat)
        lines = {
            "/entrada": tr_env._(
                "/entrada [HH:MM] - Record your arrival. The time is optional."
            ),
            "/salida": tr_env._(
                "/salida [HH:MM] - Record your departure. The time is optional."
            ),
            "/comida": tr_env._(
                "/comida [HH:MM] - Record the start of your lunch. The time is "
                "optional."
            ),
            "/regresocomida": tr_env._(
                "/regresocomida [HH:MM] - Record your return from lunch. The time "
                "is optional."
            ),
        }
        attendance_cmds = [
            line
            for command, line in lines.items()
            if self._offers_command(bot, chat, command, partner, internal_user)
        ]
        if not attendance_cmds:
            return []
        return [(tr_env._("Attendance Commands"), attendance_cmds)]

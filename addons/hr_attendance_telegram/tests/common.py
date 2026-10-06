import logging
from datetime import UTC, datetime, timedelta

from odoo.fields import Command
from odoo.libs.datetime import timezone
from odoo.tools.date_utils import utcnow

from odoo.addons.telegram.tests.common import TelegramBotTestCase

_logger = logging.getLogger(__name__)


class AttendanceTelegramTestCase(TelegramBotTestCase):
    @classmethod
    def _ensure_hr_version_column_defaults(cls):
        try:
            cls.env.cr.execute("""
                DO $$
                BEGIN
                    -- Set defaults for l10n_mx_payroll module fields
                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='hr_version'
                               AND column_name='l10n_mx_payment_period_vouchers') THEN
                        ALTER TABLE hr_version
                        ALTER COLUMN l10n_mx_payment_period_vouchers
                        SET DEFAULT 'none';
                    END IF;

                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='hr_version'
                               AND column_name='l10n_mx_regime_type') THEN
                        ALTER TABLE hr_version
                        ALTER COLUMN l10n_mx_regime_type
                        SET DEFAULT '02';
                    END IF;

                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='hr_version'
                               AND column_name='l10n_mx_shift_type') THEN
                        ALTER TABLE hr_version
                        ALTER COLUMN l10n_mx_shift_type
                        SET DEFAULT 'diurnal';
                    END IF;
                END $$;
                """)
        except Exception:
            _logger.debug("Could not set hr_version column defaults for test setup")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls._ensure_hr_version_column_defaults()

        cls.test_employee = cls.env["hr.employee"].create(
            {
                "name": "Test Employee",
                "user_id": cls.test_user.id,
            }
        )

        cls.test_calendar = cls.env["resource.calendar"].create(
            {
                "name": "Test Calendar",
                "attendance_ids": [
                    Command.create(
                        {
                            "name": "Monday",
                            "dayofweek": "0",
                            "hour_from": 8.0,
                            "hour_to": 17.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Tuesday",
                            "dayofweek": "1",
                            "hour_from": 8.0,
                            "hour_to": 17.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Wednesday",
                            "dayofweek": "2",
                            "hour_from": 8.0,
                            "hour_to": 17.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Thursday",
                            "dayofweek": "3",
                            "hour_from": 8.0,
                            "hour_to": 17.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Friday",
                            "dayofweek": "4",
                            "hour_from": 8.0,
                            "hour_to": 17.0,
                        }
                    ),
                ],
            }
        )

        cls.test_employee.resource_calendar_id = cls.test_calendar

        cls.test_user.tz = "America/Mexico_City"

    @classmethod
    def yesterday_utc(cls, hour=9, minute=0):
        user_tz = timezone("America/Mexico_City")
        today_local = datetime.now(user_tz).date()
        yesterday_local_naive = datetime.combine(
            today_local - timedelta(days=1),
            datetime.min.time().replace(hour=hour, minute=minute),
        )
        yesterday_local = yesterday_local_naive.replace(tzinfo=user_tz)
        return yesterday_local.astimezone(UTC).replace(tzinfo=None)

    def create_attendance(
        self,
        check_in=None,
        check_out=None,
        lunch_out=None,
        lunch_in=None,
        employee=None,
    ):
        if employee is None:
            employee = self.test_employee

        if check_in is None:
            check_in = utcnow().replace(second=0, microsecond=0)

        vals = {
            "employee_id": employee.id,
            "check_in": check_in,
        }

        if check_out:
            vals["check_out"] = check_out
        if lunch_out:
            vals["lunch_out"] = lunch_out
        if lunch_in:
            vals["lunch_in"] = lunch_in

        return self.env["hr.attendance"].create(vals)

    def get_utc_datetime(self, hours_offset=0):
        return utcnow().replace(second=0, microsecond=0) + timedelta(hours=hours_offset)

    def get_local_datetime(self, hours_offset=0, tz_str="America/Mexico_City"):
        tz = timezone(tz_str)
        return datetime.now(tz).replace(second=0, microsecond=0) + timedelta(
            hours=hours_offset
        )

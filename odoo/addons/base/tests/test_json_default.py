from datetime import UTC, date, datetime, timedelta, timezone

from odoo import fields
from odoo.libs.json import dumps
from odoo.tests import BaseCase
from odoo.tools.json import json_default


class TestJsonDefaultTemporal(BaseCase):
    def _expected(self, value):
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                value = value.astimezone(UTC).replace(tzinfo=None)
            return fields.Datetime.to_string(value)
        return fields.Date.to_string(value)

    def test_datetimes_are_written_as_the_orm_writes_them(self):
        values = [
            datetime(2026, 10, 7, 12, 34, 56),
            datetime(2026, 10, 7, 12, 34, 56, 789123),
            datetime(999, 1, 2, 3, 4, 5),
            datetime(1, 1, 1),
            datetime(9999, 12, 31, 23, 59, 59, 999999),
            datetime(2026, 10, 7, 23, 30, tzinfo=timezone(timedelta(hours=-6))),
            datetime(
                2026, 3, 1, 0, 15, tzinfo=timezone(timedelta(hours=5, minutes=45))
            ),
            datetime(2026, 10, 7, 12, 0, tzinfo=UTC),
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(json_default(value), self._expected(value))

    def test_dates_are_written_as_the_orm_writes_them(self):
        for value in (
            date(2026, 10, 7),
            date(999, 1, 2),
            date(1, 1, 1),
            date(9999, 12, 31),
        ):
            with self.subTest(value=value):
                self.assertEqual(json_default(value), self._expected(value))

    def test_a_subclass_takes_the_general_path(self):
        class Moment(datetime):
            pass

        class Day(date):
            pass

        value = Moment(2026, 10, 7, 12, 34, 56, 500000)
        self.assertEqual(json_default(value), "2026-10-07 12:34:56")
        self.assertEqual(json_default(Day(2026, 10, 7)), "2026-10-07")

    def test_a_payload_carries_the_same_text(self):
        row = {
            "write_date": datetime(2026, 10, 7, 1, 2, 3, 4),
            "date": date(2026, 1, 9),
        }
        self.assertEqual(
            dumps(row, default=json_default),
            '{"write_date":"2026-10-07 01:02:03","date":"2026-01-09"}',
        )

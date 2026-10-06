from datetime import UTC, date, datetime

from odoo.exceptions import ValidationError
from odoo.tools import mute_logger

from odoo.addons.resource.tests.common import ResourceCase
from odoo.addons.test_resource.tests.common import TestResourceCommon


class TestResMixin(TestResourceCommon):
    def test_resource_has_one_owner_across_business_namespaces(self):
        with self.assertRaises(ValidationError):
            self.env["resource.test.other.owner"].create(
                {
                    "name": "Another representation",
                    "resource_id": self.john.resource_id.id,
                }
            )

    def test_an_explicit_reference_can_share_an_owned_resource(self):
        reference = self.env["resource.test.reference"].create(
            {"name": "Reference", "resource_id": self.john.resource_id.id}
        )
        self.assertEqual(reference.resource_id, self.john.resource_id)
        self.assertNotEqual(reference.copy().resource_id, self.john.resource_id)

    def test_reference_validates_type_without_an_owner(self):
        resource = self.env["resource.resource"].create({"name": "Bare human"})
        self.env["resource.test.reference"].create(
            {"name": "Reference", "resource_id": resource.id}
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            resource.type = "material"

    def test_reference_rejects_material_identity(self):
        resource = self.env["resource.resource"].create(
            {"name": "Material", "type": "material"}
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["resource.test.reference"].create(
                {"name": "Reference", "resource_id": resource.id}
            )

    def test_retirement_preserves_a_reference(self):
        resource = self.env["resource.resource"].create({"name": "Referenced human"})
        self.env["resource.test.reference"].create(
            {"name": "Reference", "resource_id": resource.id}
        )
        resource._archive_if_unused()
        self.assertTrue(resource.active)

    def test_retirement_archives_a_bare_resource(self):
        resource = self.env["resource.resource"].create({"name": "Unused human"})
        resource._archive_if_unused()
        self.assertFalse(resource.active)

    def test_work_days_data(self):
        # Looking at Jean's calendar

        # Viewing it as Jean
        data = self.jean._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 16, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {"days": 5, "hours": 40})

        # Viewing it as Bob
        data = self.bob._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.bob.tz),
            self.datetime_tz(2018, 4, 6, 16, 0, 0, tzinfo=self.bob.tz),
        )[self.bob.id]
        self.assertEqual(data, {"days": 5, "hours": 40})

        # Viewing it as Patel
        # Views from 2018/04/01 20:00:00 to 2018/04/06 12:00:00
        data = self.jean._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
            self.datetime_tz(2018, 4, 6, 16, 0, 0, tzinfo=self.patel.tz),
        )[self.jean.id]
        self.assertEqual(data, {"days": 4.5, "hours": 36})  # We see only 36 hours

        # Viewing it as John
        # Views from 2018/04/02 09:00:00 to 2018/04/07 02:00:00
        data = self.jean._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.john.tz),
            self.datetime_tz(2018, 4, 6, 16, 0, 0, tzinfo=self.john.tz),
        )[self.jean.id]
        # still showing as 5 days because of rounding, but we see only 39 hours
        self.assertEqual(data, {"days": 4.875, "hours": 39})

        # Looking at John's calendar

        # Viewing it as Jean
        # Views from 2018/04/01 15:00:00 to 2018/04/06 14:00:00
        data = self.john._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.john.id]
        self.assertEqual(data, {"days": 1.417, "hours": 13})

        # Viewing it as Patel
        # Views from 2018/04/01 11:00:00 to 2018/04/06 10:00:00
        data = self.john._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.patel.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.patel.tz),
        )[self.john.id]
        self.assertEqual(data, {"days": 1.167, "hours": 10})

        # Viewing it as John
        data = self.john._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.john.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.john.tz),
        )[self.john.id]
        self.assertEqual(data, {"days": 2, "hours": 20})

        # using Jean as a timezone reference
        data = self.john._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.john.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.john.tz),
            calendar=self.calendar_jean,
        )[self.john.id]
        self.assertEqual(data, {"days": 5, "hours": 40})

        # half days
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "half",
                "calendar_id": self.calendar_jean.id,
                "resource_id": self.jean.resource_id.id,
                "date_from": self.datetime_str(
                    2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(2018, 4, 2, 14, 0, 0, tzinfo=self.jean.tz),
            }
        )

        data = self.jean._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {"days": 4.5, "hours": 36})

        # using John as a timezone reference, leaves are outside attendances
        data = self.john._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.john.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.john.tz),
            calendar=self.calendar_jean,
        )[self.john.id]
        self.assertEqual(data, {"days": 5, "hours": 40})

        leave.unlink()

        # leave size 0
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "zero",
                "calendar_id": self.calendar_jean.id,
                "resource_id": False,
                "date_from": self.datetime_str(
                    2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            }
        )

        data = self.jean._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {"days": 5, "hours": 40})

        leave.unlink()

        # leave very small size
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "small",
                "calendar_id": self.calendar_jean.id,
                "resource_id": False,
                "date_from": self.datetime_str(
                    2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(2018, 4, 2, 10, 0, 1, tzinfo=self.jean.tz),
            }
        )

        data = self.jean._get_work_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data["days"], 5)
        self.assertAlmostEqual(data["hours"], 40, 2)

    def test_leaves_days_data(self):
        # Jean takes a leave
        self.env["resource.schedule.exception"].create(
            {
                "name": "Jean is visiting India",
                "calendar_id": self.jean.resource_calendar_id.id,
                "resource_id": self.jean.resource_id.id,
                "date_from": self.datetime_str(
                    2018, 4, 10, 8, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(
                    2018, 4, 10, 16, 0, 0, tzinfo=self.jean.tz
                ),
            }
        )

        # John takes a leave for Jean
        self.env["resource.schedule.exception"].create(
            {
                "name": "Jean is comming in USA",
                "calendar_id": self.jean.resource_calendar_id.id,
                "resource_id": self.jean.resource_id.id,
                "date_from": self.datetime_str(
                    2018, 4, 12, 8, 0, 0, tzinfo=self.john.tz
                ),
                "date_to": self.datetime_str(
                    2018, 4, 12, 16, 0, 0, tzinfo=self.john.tz
                ),
            }
        )

        # Jean asks to see how much leave he has taken
        data = self.jean._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.jean.tz),
        )[self.jean.id]
        # Sees only 1 day and 8 hours because, as john is in UTC-7 the second leave is not in
        # the attendances of Jean
        self.assertEqual(data, {"days": 1, "hours": 8})

        # Patel Asks to see when Jean has taken some leaves
        # Patel should see the same
        data = self.jean._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.patel.tz),
            self.datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.patel.tz),
        )[self.jean.id]
        self.assertEqual(data, {"days": 1, "hours": 8})

        # use Patel as a resource, jean's leaves are not visible
        datas = self.patel._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.patel.tz),
            self.datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.patel.tz),
            calendar=self.calendar_jean,
        )[self.patel.id]
        self.assertEqual(datas["days"], 0)
        self.assertEqual(datas["hours"], 0)

        # Jean takes a leave for John
        # Gives 3 hours (3/8 of a day)
        self.env["resource.schedule.exception"].create(
            {
                "name": "John is sick",
                "calendar_id": self.john.resource_calendar_id.id,
                "resource_id": self.john.resource_id.id,
                "date_from": self.datetime_str(
                    2018, 4, 10, 0, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(
                    2018, 4, 10, 20, 0, 0, tzinfo=self.jean.tz
                ),
            }
        )

        # John takes a leave
        # Gives all day (12 hours)
        self.env["resource.schedule.exception"].create(
            {
                "name": "John goes to holywood",
                "calendar_id": self.john.resource_calendar_id.id,
                "resource_id": self.john.resource_id.id,
                "date_from": self.datetime_str(
                    2018, 4, 13, 7, 0, 0, tzinfo=self.john.tz
                ),
                "date_to": self.datetime_str(
                    2018, 4, 13, 18, 0, 0, tzinfo=self.john.tz
                ),
            }
        )

        # John asks how much leaves he has
        # He sees that he has only 15 hours of leave in his attendances
        data = self.john._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.john.tz),
            self.datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.john.tz),
        )[self.john.id]
        self.assertEqual(data, {"days": 0.958, "hours": 10})

        # half days
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "half",
                "calendar_id": self.calendar_jean.id,
                "resource_id": self.jean.resource_id.id,
                "date_from": self.datetime_str(
                    2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(2018, 4, 2, 14, 0, 0, tzinfo=self.jean.tz),
            }
        )

        data = self.jean._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {"days": 0.5, "hours": 4})

        leave.unlink()

        # leave size 0
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "zero",
                "calendar_id": self.calendar_jean.id,
                "resource_id": False,
                "date_from": self.datetime_str(
                    2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            }
        )

        data = self.jean._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data, {"days": 0, "hours": 0})

        leave.unlink()

        # leave very small size
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "small",
                "calendar_id": self.calendar_jean.id,
                "resource_id": False,
                "date_from": self.datetime_str(
                    2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(2018, 4, 2, 10, 0, 1, tzinfo=self.jean.tz),
            }
        )

        data = self.jean._get_leave_duration_data_batch(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(data["days"], 0)
        self.assertAlmostEqual(data["hours"], 0, 2)

        leave.unlink()

    def test_list_work_time_per_day(self):
        working_time = self.john._get_work_time_per_day(
            self.datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.john.tz),
            self.datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.john.tz),
        )[self.john.id]
        self.assertEqual(
            working_time,
            [
                (date(2018, 4, 10), 8),
                (date(2018, 4, 13), 12),
            ],
        )

        # change john's resource's timezone
        self.john.resource_id.tz = "Europe/Brussels"
        self.assertEqual(self.john.tz, "Europe/Brussels")
        self.assertEqual(self.calendar_john.tz, "America/Los_Angeles")
        working_time = self.john._get_work_time_per_day(
            self.datetime_tz(2018, 4, 9, 0, 0, 0, tzinfo=self.john.tz),
            self.datetime_tz(2018, 4, 13, 23, 59, 59, tzinfo=self.john.tz),
        )[self.john.id]
        self.assertEqual(
            working_time,
            [
                (date(2018, 4, 10), 8),
                (date(2018, 4, 13), 12),
            ],
        )

        # half days
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "small",
                "calendar_id": self.jean.resource_calendar_id.id,
                "resource_id": self.jean.resource_id.id,
                "date_from": self.datetime_str(
                    2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(2018, 4, 2, 14, 0, 0, tzinfo=self.jean.tz),
            }
        )

        working_time = self.jean._get_work_time_per_day(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(
            working_time,
            [
                (date(2018, 4, 2), 4),
                (date(2018, 4, 3), 8),
                (date(2018, 4, 4), 8),
                (date(2018, 4, 5), 8),
                (date(2018, 4, 6), 8),
            ],
        )

        leave.unlink()

        # very small size
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "small",
                "calendar_id": self.jean.resource_calendar_id.id,
                "resource_id": self.jean.resource_id.id,
                "date_from": self.datetime_str(
                    2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(2018, 4, 2, 10, 0, 1, tzinfo=self.jean.tz),
            }
        )

        working_time = self.jean._get_work_time_per_day(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(len(working_time), 5)
        self.assertEqual(working_time[0][0], date(2018, 4, 2))
        self.assertAlmostEqual(working_time[0][1], 8, 2)

        leave.unlink()

        # size 0
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "zero",
                "calendar_id": self.jean.resource_calendar_id.id,
                "resource_id": self.jean.resource_id.id,
                "date_from": self.datetime_str(
                    2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz
                ),
                "date_to": self.datetime_str(2018, 4, 2, 10, 0, 0, tzinfo=self.jean.tz),
            }
        )

        working_time = self.jean._get_work_time_per_day(
            self.datetime_tz(2018, 4, 2, 0, 0, 0, tzinfo=self.jean.tz),
            self.datetime_tz(2018, 4, 6, 23, 0, 0, tzinfo=self.jean.tz),
        )[self.jean.id]
        self.assertEqual(
            working_time,
            [
                (date(2018, 4, 2), 8),
                (date(2018, 4, 3), 8),
                (date(2018, 4, 4), 8),
                (date(2018, 4, 5), 8),
                (date(2018, 4, 6), 8),
            ],
        )

        leave.unlink()

    def test_created_records_carry_no_creation_context(self):
        record = self.env["resource.test"].create({"name": "Fresh"})
        self.assertNotIn("check_idempotence", record.env.context)
        self.assertNotIn("check_idempotence", record.resource_id.env.context)


class TestMixinIdentity(ResourceCase):
    def test_attaching_to_a_resource_keeps_its_company_and_calendar(self):
        """A consumer must not repoint the resource it attaches to.

        ``company_id`` and ``resource_calendar_id`` are stored, writable
        *related* fields, so the defaults they used to carry were written
        straight through onto the resource at create time -- handing a
        company-A resource the acting company's schedule, silently.
        """
        resource = self._resource(name="Keeps its calendar")
        record = self.env["resource.test"].create(
            {"name": "attached", "resource_id": resource.id}
        )
        self.assertEqual(resource.calendar_id, self.calendar)
        self.assertEqual(resource.company_id, self.company)
        self.assertEqual(record.resource_calendar_id, self.calendar)
        self.assertEqual(record.company_id, self.company)

    def test_fully_flexible_leave_days_count_inclusively(self):
        """One whole day is one day, not zero."""
        record = self.env["resource.test"].create({"name": "flex"})
        record.resource_id.calendar_id = False
        self.assertFalse(
            record._get_leave_duration_data_batch(
                datetime(2026, 3, 2, 0, 0).replace(tzinfo=UTC),
                datetime(2026, 3, 6, 23, 59, 59).replace(tzinfo=UTC),
            )[record.id]["days"],
            "an absence is a leave, not the window asked about",
        )
        self.env["resource.schedule.exception"].create(
            {
                "name": "Week off",
                "resource_id": record.resource_id.id,
                "date_from": datetime(2026, 3, 2, 0, 0),
                "date_to": datetime(2026, 3, 6, 23, 59, 59),
            }
        )
        one_day = record._get_leave_duration_data_batch(
            datetime(2026, 3, 2, 0, 0).replace(tzinfo=UTC),
            datetime(2026, 3, 2, 23, 59, 59).replace(tzinfo=UTC),
        )
        self.assertEqual(one_day[record.id]["days"], 1)
        five_days = record._get_leave_duration_data_batch(
            datetime(2026, 3, 2, 0, 0).replace(tzinfo=UTC),
            datetime(2026, 3, 6, 23, 59, 59).replace(tzinfo=UTC),
        )
        self.assertEqual(five_days[record.id]["days"], 5)

    def test_a_resource_has_one_owner_and_a_batch_answers_each(self):
        # a resource has one owner (mixin.resource.resource_id is unique):
        # two records of one model cannot share it, and a batch over records
        # of distinct resources answers every one of them
        one = self._resource(name="One")
        first = self.env["resource.test"].create(
            {"name": "first", "resource_id": one.id, "company_id": self.company.id}
        )
        with self.assertRaises(ValidationError), mute_logger("odoo.db.cursor"):
            with self.env.cr.savepoint():
                self.env["resource.test"].create(
                    {
                        "name": "second",
                        "resource_id": one.id,
                        "company_id": self.company.id,
                    }
                )
        second = self.env["resource.test"].create(
            {
                "name": "second",
                "resource_id": self._resource(name="Other").id,
                "company_id": self.company.id,
            }
        )
        window = (
            datetime(2026, 3, 2).replace(tzinfo=UTC),
            datetime(2026, 3, 7).replace(tzinfo=UTC),
        )
        work = (first | second)._get_work_duration_data_batch(*window)
        leave = (first | second)._get_leave_duration_data_batch(*window)
        for result in (work, leave):
            self.assertEqual(set(result), {first.id, second.id})
            self.assertEqual(result[first.id], result[second.id])


class TestMixinDaysWithoutCalendar(ResourceCase):
    def test_leave_days_count_the_days_the_leave_touches(self):
        host = self.env["resource.test"].create(
            {"name": "Flexible", "resource_calendar_id": False}
        )
        self.assertEqual(host.resource_calendar_id.schedule_type, "fully_flexible")
        self.env["resource.schedule.exception"].create(
            {
                "name": "Day off",
                "resource_id": host.resource_id.id,
                "date_from": datetime(2026, 10, 5),
                "date_to": datetime(2026, 10, 5, 23, 59, 59),
            }
        )
        monday = datetime(2026, 10, 5, tzinfo=UTC)
        for stop in (
            datetime(2026, 10, 6, tzinfo=UTC),
            datetime(2026, 10, 5, 23, 59, 59, tzinfo=UTC),
        ):
            with self.subTest(stop=stop):
                data = host._get_leave_duration_data_batch(monday, stop)[host.id]
                self.assertEqual(data["days"], 1)

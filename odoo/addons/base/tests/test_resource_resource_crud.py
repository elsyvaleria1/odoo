from datetime import UTC, date, datetime, timedelta

from psycopg import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, counting_statements, tagged
from odoo.tools import mute_logger


@tagged("at_install", "-post_install")
class TestResourceResourceCrud(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "CRUD Calendar", "tz": "Europe/Brussels"}
        )
        cls.user = cls.env["res.users"].create(
            {"name": "Resource User", "login": "res_crud_user", "tz": "Asia/Tokyo"}
        )
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Machine", "calendar_id": cls.calendar.id}
        )

    def _count_queries_to_create(self, count):
        companies = self.env["res.company"].create(
            [{"name": f"Batch {count} {index}"} for index in range(count)]
        )
        users = self.env["res.users"].create(
            [
                {"name": f"Batch {count} {index}", "login": f"batch_{count}_{index}"}
                for index in range(count)
            ]
        )
        vals_list = [
            {"type": "human", "user_id": user.id, "company_id": company.id}
            for user, company in zip(users, companies, strict=True)
        ]
        self.env.flush_all()
        self.env.invalidate_all()
        with counting_statements(self.env.cr) as statements:
            self.env["resource.resource"].create(vals_list)
            self.env.flush_all()
            return statements.count

    def test_a_batch_reads_its_users_and_companies_once(self):
        self.assertEqual(
            self._count_queries_to_create(4), self._count_queries_to_create(1)
        )

    def test_copy_appends_copy_to_name(self):
        copy = self.resource.copy()
        self.assertIn("(copy)", str(copy.name))

    def test_the_default_schedule_is_the_records_company(self):
        company = self.env["res.company"].create({"name": "Default here"})
        resource = (
            self.env["resource.resource"]
            .with_context(default_company_id=company.id)
            .create({"name": "Born elsewhere", "type": "material"})
        )
        self.assertEqual(resource.company_id, company)
        self.assertEqual(resource.calendar_id, company.resource_calendar_id)

    def test_a_company_change_takes_its_schedule(self):
        company = self.env["res.company"].create({"name": "Moved here"})
        self.calendar.company_id = self.env.company
        self.resource.company_id = company
        self.assertEqual(self.resource.calendar_id, company.resource_calendar_id)

    def test_a_users_resource_without_company_is_found(self):
        other = self.env["res.company"].create({"name": "Other"})
        anywhere, _other = self.env["resource.resource"].create(
            [
                {"name": "Anywhere", "user_id": self.user.id, "company_id": False},
                {"name": "Other", "user_id": self.user.id, "company_id": other.id},
            ]
        )
        self.assertEqual(self.user._get_company_resource(), anywhere)

    def test_create_inherits_tz_from_calendar(self):
        resource = self.env["resource.resource"].create(
            {"name": "Machine 2", "calendar_id": self.calendar.id}
        )
        self.assertEqual(resource.tz, "Europe/Brussels")

    def test_write_idempotence_skips_noop(self):
        unchanged = {"name": self.resource.name, "tz": self.resource.tz}
        self.env.flush_all()
        with self.assertQueryCount(0):
            self.resource.with_context(check_idempotence=True).write(unchanged)
            self.env.flush_all()

    def test_compute_avatar_follows_user(self):
        self.resource.user_id = self.user
        self.assertEqual(self.resource.avatar_128, self.user.avatar_128)

    def test_onchange_company_sets_calendar(self):
        resource = self.env["resource.resource"].new(
            {"company_id": self.env.company.id}
        )
        resource._onchange_company_id()
        self.assertEqual(resource.calendar_id, self.env.company.resource_calendar_id)

    def test_an_empty_schedule_is_the_fully_flexible_one(self):
        fully_flexible = self.env.ref("base.resource_calendar_fully_flexible")
        resource = self.env["resource.resource"].create(
            {"name": "Anytime", "calendar_id": False}
        )
        self.assertEqual(resource.calendar_id, fully_flexible)
        self.assertTrue(resource._is_fully_flexible())
        self.resource.write({"calendar_id": False})
        self.assertEqual(self.resource.calendar_id, fully_flexible)

    def test_a_company_without_hours_gives_the_fully_flexible_schedule(self):
        company = self.env["res.company"].create({"name": "No hours"})
        company.resource_calendar_id = False
        resource = self.env["resource.resource"].new({"company_id": company.id})
        resource._onchange_company_id()
        self.assertEqual(resource.calendar_id.schedule_type, "fully_flexible")

    def test_only_a_schedule_without_hours_goes_without_a_zone(self):
        self.assertFalse(self.env.ref("base.resource_calendar_fully_flexible").tz)
        with self.assertRaises(ValidationError):
            self.env["resource.calendar"].create({"name": "Zoneless", "tz": False})
        resource = self.env["resource.resource"].create(
            {"name": "Anywhere", "calendar_id": False, "tz": "Asia/Tokyo"}
        )
        self.assertEqual(resource.tz, "Asia/Tokyo")

    def test_the_fully_flexible_schedule_cannot_be_deleted(self):
        with self.assertRaises(UserError):
            self.env.ref("base.resource_calendar_fully_flexible").unlink()

    def test_choosing_a_user_does_not_move_the_work_zone(self):
        resource = self.env["resource.resource"].create(
            {"name": "Deployed", "tz": "America/Mazatlan"}
        )
        self.user.tz = "Europe/Brussels"
        resource.user_id = self.user
        self.assertEqual(resource.tz, "America/Mazatlan")

    @mute_logger("odoo.db.cursor")
    def test_create_zero_time_efficiency_violates_check(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["resource.resource"].create(
                {
                    "name": "Zero Efficiency",
                    "calendar_id": self.calendar.id,
                    "time_efficiency": 0,
                }
            )
            self.env["resource.resource"].flush_model()


@tagged("post_install", "-at_install")
class TestResourceZoneSeeding(TransactionCase):
    def test_a_falsy_tz_in_the_values_is_seeded_not_inserted(self):
        calendar = self.env["resource.calendar"].create(
            {"name": "Seed 40h", "tz": "Europe/Brussels"}
        )
        user = self.env["res.users"].create(
            {"name": "No Zone", "login": "no_zone_seed", "tz": False}
        )
        self.assertFalse(user.tz)
        resource = self.env["resource.resource"].create(
            {
                "name": user.name,
                "user_id": user.id,
                "calendar_id": calendar.id,
                "tz": user.tz,
            }
        )
        self.assertEqual(resource.tz, "Europe/Brussels")

    def test_local_day_follows_the_working_zone_across_a_clock_change(self):
        resource = self.env["resource.resource"].create(
            {"name": "Brussels", "tz": "Europe/Brussels"}
        )
        spring = date(2026, 3, 29)
        start, stop = resource._get_local_day_bounds(spring)
        self.assertEqual(
            (start, stop), (datetime(2026, 3, 28, 23, 0), datetime(2026, 3, 29, 22, 0))
        )
        self.assertEqual(stop - start, timedelta(hours=23))
        self.assertEqual(
            resource._get_local_date(datetime(2026, 3, 28, 23, 30)), spring
        )
        self.assertEqual(
            resource._get_local_date(datetime(2026, 3, 29, 0, 30, tzinfo=UTC)), spring
        )
        self.assertEqual(
            resource._get_local_date(datetime(2026, 3, 28, 22, 30)), date(2026, 3, 28)
        )

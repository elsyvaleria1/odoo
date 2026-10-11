from unittest.mock import patch

from odoo import Command
from odoo.http import Request
from odoo.libs.json import dumps as json_dumps
from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install", "hr_attendance_kiosk")
class TestHrAttendanceKiosk(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_A = cls.env["res.company"].create({"name": "company_A"})
        cls.company_B = cls.env["res.company"].create({"name": "company_B"})

        cls.department_A = cls.env["hr.department"].create(
            {"name": "department_A", "company_id": cls.company_B.id}
        )

        cls.employee_A = cls.env["hr.employee"].create(
            {
                "name": "employee_A",
                "company_id": cls.company_B.id,
                "department_id": cls.department_A.id,
            }
        )
        cls.department_B = cls.env["hr.department"].create(
            {"name": "department_B", "company_id": cls.company_A.id}
        )
        cls.employee_B = cls.env["hr.employee"].create(
            {
                "name": "employee_B",
                "company_id": cls.company_A.id,
                "department_id": cls.department_B.id,
            }
        )

    def test_employee_count_kiosk(self):
        with patch.object(Request, "render", return_value=None) as render:
            self.url_open(self.company_B.hr_attendance_config_id.attendance_kiosk_url)

        render.assert_called_once()
        _template, kiosk_info = render.call_args[0]
        kiosk_info = kiosk_info["kiosk_backend_info"]
        self.assertEqual(kiosk_info["company_name"], "company_B")
        self.assertEqual(kiosk_info["departments"][0]["count"], 1)


@tagged("post_install", "-at_install", "hr_attendance_kiosk")
class TestKioskRouteAuthorisation(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Kiosk Auth"})
        cls.other_company = cls.env["res.company"].create({"name": "Kiosk Other"})
        cls.badged = cls.env["hr.employee"].create(
            {
                "name": "Already Badged",
                "company_id": cls.company.id,
                "barcode": "EXISTINGBADGE",
            }
        )
        cls.unbadged = cls.env["hr.employee"].create(
            {"name": "No Badge Yet", "company_id": cls.company.id}
        )

    def _call(self, route, **params):
        response = self.url_open(
            route,
            data=json_dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"},
        )
        return response.json().get("result")

    @property
    def _token(self):
        return self.company.sudo().hr_attendance_config_id.attendance_kiosk_key

    def _menu_as(self, login, group):
        self.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "password": login,
                "group_ids": [
                    Command.link(self.env.ref("base.group_user").id),
                    Command.link(self.env.ref(group).id),
                ],
            }
        )
        self.authenticate(login, login)
        return self.url_open(
            f"/hr_attendance/kiosk_mode_menu/{self.env.company.id}",
            allow_redirects=False,
        )

    def test_the_kiosk_menu_sends_a_reader_of_the_kiosk_key_to_the_kiosk(self):
        response = self._menu_as(
            "kiosk_officer", "hr_attendance.group_hr_attendance_user"
        )
        key = self.env.company.hr_attendance_config_id.attendance_kiosk_key
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith(f"/hr_attendance/{key}"))

    def test_the_kiosk_menu_shows_no_kiosk_to_who_may_not_read_its_key(self):
        response = self._menu_as("kiosk_bystander", "base.group_user")
        key = self.env.company.hr_attendance_config_id.attendance_kiosk_key
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(key, response.text)

    def test_set_badge_does_not_reassign_an_existing_badge(self):
        result = self._call(
            "/hr_attendance/set_badge",
            employee_id=self.badged.id,
            badge="STOLENBADGE",
            token=self._token,
        )
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(
            self.badged.sudo().barcode,
            "EXISTINGBADGE",
            "the existing badge must survive the call",
        )

    def test_set_badge_is_not_granted_by_the_token_alone(self):
        result = self._call(
            "/hr_attendance/set_badge",
            employee_id=self.unbadged.id,
            badge="NEWBADGE",
            token=self._token,
        )
        self.assertNotEqual(result.get("status"), "success")
        self.assertFalse(
            self.unbadged.sudo().barcode,
            "possession of the kiosk token is not authority to assign a badge",
        )

    def test_set_badge_works_for_a_user_who_may_write(self):
        self.authenticate("admin", "admin")
        self.env["res.users"].browse(2).company_ids = [
            Command.link(self.company.id),
        ]
        self.env.flush_all()
        result = self._call(
            "/hr_attendance/set_badge",
            employee_id=self.unbadged.id,
            badge="NEWBADGE",
            token=self._token,
        )
        self.assertEqual(result.get("status"), "success")
        self.assertEqual(self.unbadged.sudo().barcode, "NEWBADGE")

    def test_set_settings_targets_the_company_the_token_names(self):
        self.authenticate("admin", "admin")
        admin = self.env["res.users"].browse(2)
        admin.company_ids = [
            Command.link(self.company.id),
            Command.link(self.other_company.id),
        ]
        admin.company_id = self.other_company
        before = self.other_company.hr_attendance_config_id.attendance_kiosk_mode
        self.env.flush_all()
        self._call("/hr_attendance/set_settings", token=self._token, mode="manual")
        self.assertEqual(
            self.company.hr_attendance_config_id.attendance_kiosk_mode, "manual"
        )
        self.assertEqual(
            self.other_company.hr_attendance_config_id.attendance_kiosk_mode,
            before,
            "the caller's own company must be left alone",
        )

    def test_set_settings_rejects_a_mode_that_is_not_one(self):
        self.authenticate("admin", "admin")
        self.env["res.users"].browse(2).company_ids = [Command.link(self.company.id)]
        before = self.company.hr_attendance_config_id.attendance_kiosk_mode
        self.env.flush_all()
        result = self._call(
            "/hr_attendance/set_settings", token=self._token, mode="not_a_mode"
        )
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(
            self.company.hr_attendance_config_id.attendance_kiosk_mode, before
        )

    def test_an_invalid_token_reaches_nothing(self):
        result = self._call(
            "/hr_attendance/set_badge",
            employee_id=self.unbadged.id,
            badge="X",
            token="not-a-token",
        )
        self.assertEqual(result.get("status"), "error")
        self.assertFalse(self.unbadged.sudo().barcode)

    def test_a_falsy_token_reaches_nothing(self):
        field = self.env["hr_attendance.config"]._fields["attendance_kiosk_key"]
        in_not_null = field in self.registry.not_null_fields
        self.registry.not_null_fields.discard(field)
        if in_not_null:
            self.addCleanup(self.registry.not_null_fields.add, field)
        self.env.cr.execute(
            "ALTER TABLE hr_attendance_config "
            "ALTER COLUMN attendance_kiosk_key DROP NOT NULL"
        )
        self.env.cr.execute(
            "UPDATE hr_attendance_config SET attendance_kiosk_key = NULL "
            "WHERE company_id = %s",
            (self.company.id,),
        )
        self.env.invalidate_all()

        self.assertEqual(
            self.env["hr_attendance.config"]
            .sudo()
            .search([("attendance_kiosk_key", "=", False)])
            .company_id.ids,
            self.company.ids,
            "the fixture no longer reproduces a nullable key; the assertions "
            "below would pass against any code",
        )

        attendances_before = self.env["hr.attendance"].search_count([])
        for token in (None, False, ""):
            with self.subTest(token=token, route="attendance_employee_data"):
                result = self._call(
                    "/hr_attendance/attendance_employee_data",
                    employee_id=self.badged.id,
                    token=token,
                )
                self.assertEqual(result.get("status"), "error")
                self.assertNotIn("employee_name", result)

            with self.subTest(token=token, route="employees_infos"):
                result = self._call(
                    "/hr_attendance/employees_infos",
                    token=token,
                    limit=10,
                    offset=0,
                    domain=[],
                )
                self.assertEqual(result.get("status"), "error")
                self.assertFalse(result.get("records"))

            with self.subTest(token=token, route="manual_selection"):
                result = self._call(
                    "/hr_attendance/manual_selection",
                    token=token,
                    employee_id=self.badged.id,
                    pin_code=False,
                )
                self.assertEqual(result.get("status"), "error")

            with self.subTest(token=token, route="attendance_barcode_scanned"):
                result = self._call(
                    "/hr_attendance/attendance_barcode_scanned",
                    token=token,
                    barcode="EXISTINGBADGE",
                )
                self.assertEqual(result.get("status"), "error")

        self.assertEqual(self.env["hr.attendance"].search_count([]), attendances_before)
        self.assertFalse(self.badged.sudo().attendance_ids)

    def test_a_required_key_makes_the_falsy_domain_match_nothing(self):
        field = self.env["hr_attendance.config"]._fields["attendance_kiosk_key"]
        self.assertTrue(field.required)
        self.assertIn(field, self.registry.not_null_fields)
        self.assertFalse(
            self.env["hr_attendance.config"]
            .sudo()
            .search([("attendance_kiosk_key", "=", False)])
        )


@tagged("post_install", "-at_install", "hr_attendance_kiosk")
class TestKioskSettingsModeIsNotSelfServe(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Trial Mode Co"})

    def _kiosk_mode_for(self, query=""):
        with patch.object(Request, "render", return_value=None) as render:
            self.url_open(
                self.company.sudo().hr_attendance_config_id.attendance_kiosk_url + query
            )
        render.assert_called_once()
        _template, info = render.call_args[0]
        return info["kiosk_backend_info"]["kiosk_mode"]

    def test_an_anonymous_visitor_gets_the_configured_kiosk_mode(self):
        self.assertEqual(
            self._kiosk_mode_for(),
            self.company.hr_attendance_config_id.attendance_kiosk_mode,
        )

    def test_from_trial_mode_is_supplied_by_the_caller(self):
        self.assertEqual(
            self._kiosk_mode_for("?from_trial_mode=True"),
            "settings",
            "an anonymous caller reaches the settings screen just by asking",
        )


@tagged("post_install", "-at_install", "hr_attendance_kiosk")
class TestKioskMenuItem(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        new_test_user(
            cls.env,
            login="kiosk_officer",
            groups="base.group_user,hr_attendance.group_hr_attendance_user",
        )
        new_test_user(cls.env, login="kiosk_employee", groups="base.group_user")

    def _open_menu(self, login):
        self.authenticate(login, login)
        return self.url_open(
            f"/hr_attendance/kiosk_mode_menu/{self.company.id}", allow_redirects=False
        )

    def test_an_attendance_officer_is_sent_to_the_company_kiosk(self):
        response = self._open_menu("kiosk_officer")
        self.assertIn(response.status_code, (302, 303))
        self.assertTrue(
            response.headers["Location"].endswith(
                self.company.hr_attendance_config_id.attendance_kiosk_url.split("/", 3)[
                    3
                ]
            )
        )

    def test_an_employee_without_the_kiosk_key_is_refused(self):
        self.assertEqual(self._open_menu("kiosk_employee").status_code, 404)

from uuid import uuid4

from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tests import common


@common.tagged("web_http", "web_session")
class TestSessionInfo(common.HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "A"})
        cls.company_b = cls.env["res.company"].create({"name": "B"})
        cls.company_c = cls.env["res.company"].create({"name": "C"})
        cls.company_b_branch = cls.env["res.company"].create(
            {"name": "B Branch", "parent_id": cls.company_b.id}
        )
        cls.company_c_branch = cls.env["res.company"].create(
            {"name": "C Branch", "parent_id": cls.company_c.id}
        )
        cls.company_c_branch_branch = cls.env["res.company"].create(
            {"name": "C Branch Branch", "parent_id": cls.company_c_branch.id}
        )
        cls.allowed_companies = (
            cls.company_a
            + cls.company_b_branch
            + cls.company_c
            + cls.company_c_branch_branch
        )
        cls.disallowed_ancestor_companies = cls.company_b + cls.company_c_branch

        cls.user_password = "info"
        cls.user = common.new_test_user(
            cls.env,
            "session",
            email="session@in.fo",
            password=cls.user_password,
            tz="UTC",
        )
        cls.user.write(
            {
                "company_id": cls.company_a.id,
                "company_ids": [Command.set(cls.allowed_companies.ids)],
            }
        )

        cls.payload = json_dumps(
            {"jsonrpc": "2.0", "method": "call", "id": str(uuid4())}
        )
        cls.headers = {
            "Content-Type": "application/json",
        }

    def test_session_info(self):
        self.authenticate(self.user.login, self.user_password)
        self.env["res.users.settings"]._get_or_create_for_user(self.user)
        response = self.url_open(
            "/web/session/get_session_info",
            data=self.payload,
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        result = data["result"]

        expected_allowed_companies = {
            str(company.id): {
                "id": company.id,
                "name": company.name,
                "sequence": company.sequence,
                "child_ids": company.child_ids.ids,
                "currency_id": company.currency_id.id,
                "parent_id": company.parent_id.id,
            }
            for company in self.allowed_companies
        }

        expected_disallowed_ancestor_companies = {
            str(company.id): {
                "id": company.id,
                "name": company.name,
                "sequence": company.sequence,
                "child_ids": company.child_ids.ids,
                "parent_id": company.parent_id.id,
            }
            for company in self.disallowed_ancestor_companies
        }

        expected_user_companies = {
            "current_company": self.company_a.id,
            "allowed_companies": expected_allowed_companies,
            "disallowed_ancestor_companies": expected_disallowed_ancestor_companies,
        }
        # session_info()["groups"] is an extension point: an addon's ir.http adds
        # the groups its client reads at boot. web owns one key of it.
        self.assertEqual(
            result["groups"]["base.group_allow_export"],
            self.user.has_group("base.group_allow_export"),
        )
        # user_companies is an extension point too (hr_timesheet adds two keys per
        # company); web owns the keys declared above, not the whole dict
        user_companies = result["user_companies"]
        self.assertEqual(
            user_companies["current_company"],
            expected_user_companies["current_company"],
        )
        for key in ("allowed_companies", "disallowed_ancestor_companies"):
            self.assertEqual(
                {
                    company_id: {
                        field: value
                        for field, value in company.items()
                        if field in expected_user_companies[key][company_id]
                    }
                    for company_id, company in user_companies[key].items()
                },
                expected_user_companies[key],
                f"The session_info['user_companies']['{key}'] does not have the "
                "expected structure",
            )

    def test_session_info_hands_a_user_without_settings_a_writable_settings_id(
        self,
    ):
        user = common.new_test_user(
            self.env,
            "session_first",
            password="session_first",
            groups="base.group_portal",
        )
        self.assertFalse(user.res_users_settings_ids)
        self.authenticate(user.login, "session_first")

        response = self.url_open(
            "/web/session/get_session_info", data=self.payload, headers=self.headers
        )

        settings_id = response.json()["result"]["user_settings"]["id"]
        self.assertIsInstance(settings_id, int)
        self.assertEqual(user.res_users_settings_ids.id, settings_id)

    def test_session_modules(self):
        self.authenticate(self.user.login, self.user_password)
        response = self.url_open(
            "/web/session/modules", data=self.payload, headers=self.headers
        )
        data = response.json()
        self.assertIsInstance(data["result"], list)

    def test_session_info_carries_a_sanitized_sysadmin_message_and_no_subscription(
        self,
    ):
        set_param = self.env["ir.config_parameter"].sudo().set_param
        set_param(
            "sysadmin.message",
            json_dumps(
                {
                    "message": "<b>Downtime</b><script>alert(1)</script>",
                    "warning_type": "user",
                }
            ),
        )
        set_param("database.expiration_date", "2000-01-01 00:00:00")
        self.authenticate(self.user.login, self.user_password)
        result = self.url_open(
            "/web/session/get_session_info", data=self.payload, headers=self.headers
        ).json()["result"]
        message = result["sysadmin_message"]
        self.assertEqual(message["warning_type"], "user")
        self.assertIn("<b>Downtime</b>", message["message"])
        self.assertNotIn("script", message["message"])
        for key in ("expiration_date", "expiration_reason", "warning"):
            self.assertNotIn(key, result)

    def test_session_info_carries_the_company_home_menu_default(self):
        self.authenticate(self.user.login, self.user_password)
        response = self.url_open(
            "/web/session/get_session_info", data=self.payload, headers=self.headers
        )
        self.assertIsNone(response.json()["result"]["homemenu_default_config"])

        layout = {
            "version": 2,
            "order": [],
            "pinned": ["mail.menu_root_discuss"],
            "hidden": [],
        }
        self.company_a.web_config_id.homemenu_default_config = layout
        response = self.url_open(
            "/web/session/get_session_info", data=self.payload, headers=self.headers
        )
        self.assertEqual(response.json()["result"]["homemenu_default_config"], layout)

    def test_session_info_carries_the_company_home_tiles_default(self):
        self.authenticate(self.user.login, self.user_password)
        response = self.url_open(
            "/web/session/get_session_info", data=self.payload, headers=self.headers
        )
        self.assertIn(
            {"id": "recent_records_1", "type": "recent_records", "size": "2x1"},
            response.json()["result"]["home_tiles_default"]["tiles"],
        )

        self.company_a.web_config_id.home_tiles_default = {
            "version": 1,
            "tiles": [
                {"id": "recent_records_1", "type": "recent_records", "size": "2x1"},
                {"id": "gone_1", "type": "no_such_type"},
            ],
        }
        response = self.url_open(
            "/web/session/get_session_info", data=self.payload, headers=self.headers
        )
        self.assertEqual(
            response.json()["result"]["home_tiles_default"],
            {
                "version": 1,
                "tiles": [
                    {"id": "recent_records_1", "type": "recent_records", "size": "2x1"}
                ],
            },
        )

    def test_home_menu_default_uses_only_an_allowed_cookie_company(self):
        self.authenticate(self.user.login, self.user_password)
        self.company_a.web_config_id.homemenu_default_config = {"pinned": ["app.a"]}
        self.company_c.web_config_id.homemenu_default_config = {"pinned": ["app.c"]}
        self.company_b.web_config_id.homemenu_default_config = {
            "pinned": ["private.app"]
        }
        for cookie, expected in (
            (str(self.company_c.id), "app.c"),
            (str(self.company_b.id), "app.a"),
            ("invalid", "app.a"),
            (f"{self.company_b.id}-{self.company_c.id}", "app.c"),
        ):
            with self.subTest(cookie=cookie):
                self.opener.cookies.set("cids", cookie)
                response = self.url_open(
                    "/web/session/get_session_info",
                    data=self.payload,
                    headers=self.headers,
                )
                self.assertEqual(
                    response.json()["result"]["homemenu_default_config"]["pinned"],
                    [expected],
                )

import urllib.parse
from unittest.mock import MagicMock, call, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import freeze_time, tagged
from odoo.tests.common import users

from .common import TestDatabasesCommon


@tagged("-at_install", "post_install")
class TestSynchronization(TestDatabasesCommon):
    def mock_json2_calls_for_db(
        self, fqdn, version="dont-write-it-to-project", users=(), kpis=()
    ):
        self.json2_mocked_calls[fqdn]["version"] = version
        self.json2_mocked_calls[fqdn]["res.users"]["search_read"] = list(users)
        self.json2_mocked_calls[fqdn]["kpi.provider"]["get_kpi_summary"] = list(kpis)

    @users("db_manager@company.tld")
    def test_synchronization_disabled(self):
        self.env["credential.credential"]._set_system_secret(
            "databases.odoocom_apikey", False
        )

        self.env["project.project"].action_synchronize_all_databases()

        self.mock_requests_request.authenticate.assert_not_called()
        self.mock_requests_request.execute_kw.assert_not_called()

    @users("db_manager@company.tld")
    def test_synchronize_databases(self):
        Project = self.env["project.project"]
        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "odoo-sa",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "some_user@odoo.com",
                "version": "16.0+e",
            },
        ]
        self.mock_json2_calls_for_db("odoo-sa.my.odoo.test")
        Project.action_synchronize_all_databases()
        new_projects = Project.search([])

        self.assertCountEqual(
            self.mock_requests_request.mock_calls[:1],
            [
                call(
                    "post",
                    "https://www.odoo.com/json/2/odoo.database/list",
                    json={},
                    headers={
                        "Authorization": "Bearer privateKey",
                        "X-Odoo-Database": "openerp",
                    },
                    allow_redirects=False,
                    timeout=15,
                ),
            ],
        )
        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "some_user@odoo.com",
                    "database_version": "16.0",
                },
            ],
        )

        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "Odoo",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "other_user@odoo.com",
                "version": "17.0+e",
            },
        ]
        with self.capture_wizard() as captured:
            Project.action_synchronize_all_databases()
        self.assertEqual(Project.search([]), new_projects)
        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "Odoo",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "other_user@odoo.com",
                    "database_version": "17.0",
                },
            ],
        )

        (wizard,) = captured["wizards"]
        self.assertEqual(wizard.summary_message, "0 new databases, 1 updated.")

    @users("db_manager@company.tld")
    def test_db_synchronize_several_dbs(self):
        Project = self.env["project.project"]
        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "odoo-sa",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "some_user@odoo.com",
                "version": "16.0+e",
            },
            {
                "name": "titi-sarl",
                "url": "http://titi-sarl.my.odoo.test",
                "login": "admin@titi-sarl.fr",
                "version": "17.0+e",
            },
            {
                "name": "toto-nv",
                "url": "http://toto-nv.my.odoo.test",
                "login": "contact@toto-nv.be",
                "version": "18.0+e",
            },
        ]
        self.mock_json2_calls_for_db("odoo-sa.my.odoo.test")
        self.mock_json2_calls_for_db("titi-sarl.my.odoo.test")
        self.mock_json2_calls_for_db("toto-nv.my.odoo.test")
        with self.capture_wizard() as captured:
            Project.action_synchronize_all_databases()

        (wizard,) = captured["wizards"]
        self.assertEqual(wizard.summary_message, "3 new databases, 3 updated.")

        self.assertCountEqual(
            self.mock_requests_request.mock_calls[:1],
            [
                call(
                    "post",
                    "https://www.odoo.com/json/2/odoo.database/list",
                    json={},
                    headers={
                        "Authorization": "Bearer privateKey",
                        "X-Odoo-Database": "openerp",
                    },
                    allow_redirects=False,
                    timeout=15,
                ),
            ],
        )
        new_projects = Project.search([], order="database_version")
        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "some_user@odoo.com",
                    "database_version": "16.0",
                },
                {
                    "name": "titi-sarl",
                    "database_name": "titi-sarl",
                    "database_hosting": "saas",
                    "database_url": "http://titi-sarl.my.odoo.test",
                    "database_api_login": "admin@titi-sarl.fr",
                    "database_version": "17.0",
                },
                {
                    "name": "toto-nv",
                    "database_name": "toto-nv",
                    "database_hosting": "saas",
                    "database_url": "http://toto-nv.my.odoo.test",
                    "database_api_login": "contact@toto-nv.be",
                    "database_version": "18.0",
                },
            ],
        )

        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "Odoo",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "other_user@odoo.com",
                "version": "17.0+e",
            },
        ]
        self.mock_json2_calls_for_db("odoo-sa.my.odoo.test")
        with self.capture_wizard() as captured:
            Project.action_synchronize_all_databases()
        (wizard,) = captured["wizards"]
        self.assertEqual(wizard.summary_message, "0 new databases, 3 updated.")

        self.assertEqual(Project.search([]), new_projects)
        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "Odoo",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "other_user@odoo.com",
                    "database_version": "17.0",
                },
                {
                    "name": "titi-sarl",
                    "database_name": "titi-sarl",
                    "database_hosting": "saas",
                    "database_url": "http://titi-sarl.my.odoo.test",
                    "database_api_login": "admin@titi-sarl.fr",
                    "database_version": "17.0",
                },
                {
                    "name": "toto-nv",
                    "database_name": "toto-nv",
                    "database_hosting": "saas",
                    "database_url": "http://toto-nv.my.odoo.test",
                    "database_api_login": "contact@toto-nv.be",
                    "database_version": "18.0",
                },
            ],
        )

    def test_odoocom_db_synchronization(self):
        Project = self.env["project.project"]
        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "cron-odoo-sa",
                "url": "http://cron-odoo-sa.my.odoo.test",
                "login": "some_user@odoo.com",
                "version": "16.0+e",
            },
        ]
        self.json2_mocked_calls["cron-odoo-sa.my.odoo.test"]["version"] = "16.0+e"
        self.json2_mocked_calls["cron-odoo-sa.my.odoo.test"]["res.users"][
            "search_read"
        ] = []
        self.json2_mocked_calls["cron-odoo-sa.my.odoo.test"]["kpi.provider"][
            "get_kpi_summary"
        ] = []

        with freeze_time("2025-01-01 00:00"):
            Project._cron_sync_all_databases_with_odoocom()
        new_projects = Project.search([])

        self.assertCountEqual(
            self.mock_requests_request.mock_calls,
            [
                call(
                    "post",
                    "https://www.odoo.com/json/2/odoo.database/list",
                    json={},
                    headers={
                        "Authorization": "Bearer privateKey",
                        "X-Odoo-Database": "openerp",
                    },
                    allow_redirects=False,
                    timeout=15,
                ),
            ],
        )
        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "cron-odoo-sa",
                    "database_name": "cron-odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://cron-odoo-sa.my.odoo.test",
                    "database_api_login": "some_user@odoo.com",
                    "database_version": "16.0",
                    "database_last_synchro": False,
                },
            ],
        )

        with freeze_time("2025-01-01 00:00"):
            Project._cron_sync_all_databases()
        self.assertEqual(
            new_projects.database_last_synchro,
            fields.Datetime.from_string("2025-01-01 00:00"),
            "The database should now have been scanned",
        )

        with freeze_time("2025-01-01 23:59"):
            Project._cron_sync_all_databases()
        self.assertEqual(
            new_projects.database_last_synchro,
            fields.Datetime.from_string("2025-01-01 00:00"),
            "The database shouldn't have been scanned yet",
        )

        with freeze_time("2025-01-02 00:00"):
            Project._cron_sync_all_databases()
        self.assertEqual(
            new_projects.database_last_synchro,
            fields.Datetime.from_string("2025-01-02 00:00"),
            "The database should have been scanned",
        )

    @users("db_manager@company.tld")
    def test_synchronizing_a_saas_db_with_just_a_url_should_raise_an_error(self):
        db = self.env["project.project"].create(
            [
                {
                    "name": "An accounting DB",
                    "database_hosting": "saas",
                    "database_url": "http://anotherdb.that.doesnt.exist",
                }
            ]
        )
        with self.assertRaisesRegex(
            UserError,
            "Error while connecting to http://anotherdb.that.doesnt.exist: "
            "We are missing the database name, the api login or the api key",
        ):
            db.action_database_synchronize()

    @users("db_manager@company.tld")
    def test_synchronizing_several_db_with_one_missing_its_name_and_api_info(self):
        Project = self.env["project.project"]
        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "odoo-sa",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "some_user@odoo.com",
                "version": "16.0+e",
            },
        ]
        self.mock_json2_calls_for_db("odoo-sa.my.odoo.test")
        Project.action_synchronize_all_databases()
        Project.create(
            [
                {
                    "name": "An accounting DB",
                    "database_hosting": "saas",
                    "database_url": "http://anotherdb.that.doesnt.exist",
                }
            ]
        )
        dbs = Project.search([])
        self.assertEqual(len(dbs), 2)
        self.json2_mocked_calls["odoo-sa.my.odoo.test"]["version"] = "16.0+e"
        self.json2_mocked_calls["odoo-sa.my.odoo.test"]["res.users"]["search_read"] = []
        self.json2_mocked_calls["odoo-sa.my.odoo.test"]["kpi.provider"][
            "get_kpi_summary"
        ] = []
        with self.capture_wizard() as captured:
            dbs.action_database_synchronize()
        (wizard,) = captured["wizards"]
        self.assertEqual(
            wizard.error_message.strip(),
            "Error while connecting to http://anotherdb.that.doesnt.exist: "
            "We are missing the database name, the api login or the api key",
        )

    @users("db_manager@company.tld")
    def test_synchronizing_all_databases_shouldnt_raise_but_should_report_any_issue(
        self,
    ):
        Project = self.env["project.project"]
        Project.create(
            [
                {
                    "name": "An accounting DB",
                    "database_hosting": "saas",
                    "database_url": "http://anotherdb.that.doesnt.exist",
                }
            ]
        )
        dbs = Project.search([])
        self.assertEqual(len(dbs), 1)

        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "odoo-sa",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "some_user@odoo.com",
                "version": "16.0+e",
            },
        ]

        self.mock_json2_calls_for_db("odoo-sa.my.odoo.test")
        self.json2_mocked_calls["odoo-sa.my.odoo.test"]["version"] = "saas~18.3a1+e"

        with self.capture_wizard() as captured:
            Project.action_synchronize_all_databases()
        dbs = Project.search([])
        self.assertRecordValues(
            dbs,
            [
                {
                    "database_url": "http://anotherdb.that.doesnt.exist",
                    "database_version": False,
                },
                {
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_version": "saas~18.3",
                },
            ],
        )

        (wizard,) = captured["wizards"]
        self.assertEqual(
            wizard.error_message.strip(),
            "Error while connecting to http://anotherdb.that.doesnt.exist: "
            "We are missing the database name, the api login or the api key",
        )

    @users("db_manager@company.tld")
    def test_synchronizing_all_databases_shouldnt_raise_if_project_template_not_configured(
        self,
    ):
        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "odoo-sa",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "some_user@odoo.com",
                "version": "16.0+e",
            },
        ]
        self.env["ir.config_parameter"].sudo().set_param(
            "databases.odoocom_project_template", False
        )

        self.mock_json2_calls_for_db("odoo-sa.my.odoo.test")
        self.env["project.project"].action_synchronize_all_databases()

    @users("db_manager@company.tld")
    def test_sync_pull_db_record_already_registered_as_saas_manually(self):
        Project = self.env["project.project"]
        self.assertFalse(Project.search([]), "There shouldn't be any project yet")
        Project.create(
            [
                {
                    "name": "odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                }
            ]
        )
        db = Project.search([])
        self.assertRecordValues(
            db,
            [
                {
                    "name": "odoo-sa",
                    "database_name": False,
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": False,
                    "database_version": False,
                },
            ],
        )

        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "odoo-sa",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "some_user@odoo.com",
                "version": "16.0+e",
            },
        ]
        self.mock_json2_calls_for_db("odoo-sa.my.odoo.test")
        Project.action_synchronize_all_databases()
        self.assertRecordValues(
            db,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "some_user@odoo.com",
                    "database_version": "16.0",
                },
            ],
        )

    @users("db_manager@company.tld")
    def test_db_on_premise_configured_shouldnt_be_modified(self):
        Project = self.env["project.project"]
        self.assertFalse(Project.search([]), "There shouldn't be any project yet")
        Project.create(
            [
                {
                    "name": "odoo-sa",
                    "database_hosting": "premise",
                    "database_name": "odoo-sa",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "randomlogin@randomdomain.random",
                    "database_api_key": "random api key, amazing",
                }
            ]
        )
        db = Project.search([])
        self.assertRecordValues(
            db,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo-sa",
                    "database_hosting": "premise",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "randomlogin@randomdomain.random",
                    "database_api_key": "random api key, amazing",
                },
            ],
        )

        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "odoo-sa",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "somethingelse@wout.wout",
                "version": "16.0+e",
            },
        ]
        self.mock_json2_calls_for_db("odoo-sa.my.odoo.test")
        with self.capture_wizard() as captured:
            Project.action_synchronize_all_databases()
        self.assertRecordValues(
            db,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo-sa",
                    "database_hosting": "premise",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "randomlogin@randomdomain.random",
                    "database_api_key": "random api key, amazing",
                    "database_version": False,
                },
            ],
        )
        (wizard,) = captured["wizards"]
        self.assertEqual(
            wizard.error_message.strip(),
            "The database http://odoo-sa.my.odoo.test is registered as a saas database in odoo.com. "
            "As it seems to be configured we have left it as is.",
        )

    @users("db_manager@company.tld")
    def test_db_on_premise_not_configured_should_be_updated_to_saas_db(self):
        Project = self.env["project.project"]
        self.assertFalse(Project.search([]), "There shouldn't be any project yet")
        Project.create(
            [
                {
                    "name": "odoo-sa",
                    "database_hosting": "premise",
                    "database_url": "http://odoo-sa.my.odoo.test",
                }
            ]
        )
        db = Project.search([])
        self.assertRecordValues(
            db,
            [
                {
                    "name": "odoo-sa",
                    "database_name": False,
                    "database_hosting": "premise",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": False,
                    "database_version": False,
                },
            ],
        )

        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "odoo-sa",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "some_user@odoo.com",
                "version": "16.0+e",
            },
        ]
        self.mock_json2_calls_for_db("odoo-sa.my.odoo.test")
        Project.action_synchronize_all_databases()
        self.assertRecordValues(
            db,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "some_user@odoo.com",
                    "database_version": "16.0",
                },
            ],
        )

    @users("db_manager@company.tld")
    def test_synchronization_wizard_update_from_odoocom_without_configuration(self):
        self.env["credential.credential"]._set_system_secret(
            "databases.odoocom_apikey", False
        )

        wizard = self.env["wizard.project.project.synchronize.database"].create({})

        wizard._do_update_from_odoocom()

    @users("db_manager@company.tld")
    def test_synchronization_wizard_update_from_odoocom_with_authenticate_error(self):
        self.mock_requests_request.configure_mock(
            **{
                "side_effect": None,
                "return_value.status_code": 401,
                "return_value.json.return_value": {"message": "Invalid apikey"},
            }
        )

        wizard = self.env["wizard.project.project.synchronize.database"].create({})
        wizard._do_update_from_odoocom()
        self.assertEqual(
            wizard.error_message,
            "Error while listing databases from https://www.odoo.com: Invalid apikey\n",
        )

    @users("db_manager@company.tld")
    def test_synchronization_wizard_update_from_odoocom_with_call_error(self):
        self.mock_requests_request.configure_mock(
            **{
                "side_effect": None,
                "return_value.status_code": 422,
                "return_value.json.return_value": {"message": "Some error"},
            }
        )

        wizard = self.env["wizard.project.project.synchronize.database"].create({})
        wizard._do_update_from_odoocom()
        self.assertEqual(
            wizard.error_message,
            "Error while listing databases from https://www.odoo.com: Some error\n",
        )

    @users("db_manager@company.tld")
    def test_user_management(self):
        database = self.env["project.project"].create(
            [
                {
                    "name": "odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_name": "odoo-sa",
                    "database_api_login": "admin",
                    "database_api_key": "admin_apikey",
                }
            ]
        )
        invite_wizard = self.env["wizard.project.project.update.database.user"].create(
            {
                "mode": "invite",
                "database_ids": database.ids,
                "user_ids": self.user_employee.ids,
            }
        )

        self.json2_mocked_calls["odoo-sa.my.odoo.test"]["res.users"][
            "web_create_users"
        ] = True
        invite_wizard.action_invite_users()
        self.assertCountEqual(
            self.mock_requests_request.mock_calls,
            [
                call(
                    "post",
                    "http://odoo-sa.my.odoo.test/json/2/res.users/web_create_users",
                    json={
                        "emails": ["employee@company.tld"],
                        "context": {"no_reset_password": True},
                    },
                    headers={
                        "Authorization": "Bearer admin_apikey",
                        "X-Odoo-Database": "odoo-sa",
                    },
                    allow_redirects=False,
                    timeout=15,
                ),
            ],
        )
        self.assertFalse(invite_wizard.error_message)

        self.mock_requests_request.reset_mock()
        remove_wizard = self.env["wizard.project.project.update.database.user"].create(
            {
                "mode": "remove",
                "database_ids": database.ids,
                "user_ids": self.user_employee.ids,
            }
        )
        self.json2_mocked_calls["odoo-sa.my.odoo.test"]["res.users"]["search"] = [23]
        self.json2_mocked_calls["odoo-sa.my.odoo.test"]["res.users"]["write"] = True
        invite_wizard.action_remove_users()
        self.assertCountEqual(
            self.mock_requests_request.mock_calls,
            [
                call(
                    "post",
                    "http://odoo-sa.my.odoo.test/json/2/res.users/search",
                    json={
                        "domain": [("login", "in", ["employee@company.tld"])],
                    },
                    headers={
                        "Authorization": "Bearer admin_apikey",
                        "X-Odoo-Database": "odoo-sa",
                    },
                    allow_redirects=False,
                    timeout=15,
                ),
                call(
                    "post",
                    "http://odoo-sa.my.odoo.test/json/2/res.users/write",
                    json={
                        "ids": [23],
                        "values": {"active": False},
                    },
                    headers={
                        "Authorization": "Bearer admin_apikey",
                        "X-Odoo-Database": "odoo-sa",
                    },
                    allow_redirects=False,
                    timeout=15,
                ),
            ],
        )

        self.assertFalse(remove_wizard.error_message)

    @users("db_manager@company.tld")
    def test_synchronization_with_duplicate_property_labels(self):
        Project = self.env["project.project"]
        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = [
            {
                "name": "odoo-sa",
                "url": "http://odoo-sa.my.odoo.test",
                "login": "some_user@odoo.com",
                "version": "16.0+e",
            },
        ]
        self.mock_json2_calls_for_db(
            "odoo-sa.my.odoo.test",
            kpis=[
                {
                    "id": "my_kpi.some_unique_id",
                    "name": "Duplicate label",
                    "type": "integer",
                    "value": 1,
                },
                {
                    "id": "my_kpi.another_unique_id",
                    "name": "Duplicate label",
                    "type": "integer",
                    "value": 4,
                },
            ],
        )
        Project.action_synchronize_all_databases()
        new_projects = Project.search([])

        self.assertRecordValues(
            new_projects.sudo().database_kpi_base_definition_id,
            [
                {
                    "properties_definition": [
                        {
                            "name": "my_kpi_some_unique_id",
                            "string": "Duplicate label",
                            "type": "integer",
                            "default": 0,
                        },
                        {
                            "name": "my_kpi_another_unique_id",
                            "string": "Duplicate label",
                            "type": "integer",
                            "default": 0,
                        },
                    ],
                }
            ],
        )
        self.assertRecordValues(
            new_projects,
            [
                {
                    "database_kpi_properties": {
                        "my_kpi_some_unique_id": 1,
                        "my_kpi_another_unique_id": 4,
                    },
                }
            ],
        )


@tagged("-at_install", "post_install")
class TestXmlRpcSynchronization(TestDatabasesCommon):
    def setUp(self):
        super().setUp()

        def mock_requests_request(method, uri, *args, **kwargs):
            if urllib.parse.urlparse(uri).hostname == "www.odoo.com":
                return prev_mock_requests_request(method, uri, *args, **kwargs)
            return MagicMock(status_code=303)

        prev_mock_requests_request = self.mock_requests_request.side_effect
        self.mock_requests_request.configure_mock(side_effect=mock_requests_request)

        self.odoo_sa_xmrpc_common = MagicMock(**{"authenticate.return_value": -128})
        self.odoo_sa_xmrpc_object = MagicMock()
        self.call_resolution_per_uri = {
            "http://odoo-sa.my.odoo.test/xmlrpc/2/common": self.odoo_sa_xmrpc_common,
            "http://odoo-sa.my.odoo.test/xmlrpc/2/object": self.odoo_sa_xmrpc_object,
        }
        self.startPatcher(
            patch(
                "xmlrpc.client.ServerProxy",
                side_effect=lambda uri, **kwargs: self.call_resolution_per_uri[uri],
            )
        )

    def set_returned_databases_list(self, databases_list):
        for database in databases_list:
            self.call_resolution_per_uri.setdefault(
                f"{database['url']}/xmlrpc/2/common", MagicMock()
            ).version.configure_mock(return_value={"server_serie": database["version"]})
            self.call_resolution_per_uri.setdefault(
                f"{database['url']}/xmlrpc/2/object", MagicMock()
            )
        self.json2_mocked_calls["www.odoo.com"]["odoo.database"]["list"] = (
            databases_list
        )

    @users("db_manager@company.tld")
    def test_synchronize_databases(self):
        Project = self.env["project.project"]
        self.set_returned_databases_list(
            [
                {
                    "name": "odoo-sa",
                    "login": "some_user@odoo.com",
                    "version": "16.0+e",
                    "url": "http://odoo-sa.my.odoo.test",
                },
            ]
        )
        Project.action_synchronize_all_databases()
        new_projects = Project.search([])

        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "some_user@odoo.com",
                    "database_version": "16.0",
                },
            ],
        )

        self.set_returned_databases_list(
            [
                {
                    "name": "odoo-bis",
                    "login": "other_user@odoo.com",
                    "version": "17.0+e",
                    "url": "http://odoo-sa.my.odoo.test",
                },
            ]
        )
        with self.capture_wizard() as captured:
            Project.action_synchronize_all_databases()
        self.assertEqual(Project.search([]), new_projects)
        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo-bis",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "other_user@odoo.com",
                    "database_version": "17.0",
                },
            ],
        )

        (wizard,) = captured["wizards"]
        self.assertEqual(wizard.summary_message, "0 new databases, 1 updated.")

    @users("db_manager@company.tld")
    def test_db_synchronize_several_dbs(self):
        Project = self.env["project.project"]
        self.set_returned_databases_list(
            [
                {
                    "name": "odoo-sa",
                    "login": "some_user@odoo.com",
                    "version": "16.0+e",
                    "url": "http://odoo-sa.my.odoo.test",
                },
                {
                    "name": "titi-sarl",
                    "login": "admin@titi-sarl.fr",
                    "version": "17.0+e",
                    "url": "http://titi-sarl.my.odoo.test",
                },
                {
                    "name": "toto-nv",
                    "login": "contact@toto-nv.be",
                    "version": "18.0+e",
                    "url": "http://toto-nv.my.odoo.test",
                },
            ]
        )
        with self.capture_wizard() as captured:
            Project.action_synchronize_all_databases()

        (wizard,) = captured["wizards"]
        self.assertEqual(wizard.summary_message, "3 new databases, 3 updated.")

        new_projects = Project.search([], order="database_version")
        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "some_user@odoo.com",
                    "database_version": "16.0",
                },
                {
                    "name": "titi-sarl",
                    "database_name": "titi-sarl",
                    "database_hosting": "saas",
                    "database_url": "http://titi-sarl.my.odoo.test",
                    "database_api_login": "admin@titi-sarl.fr",
                    "database_version": "17.0",
                },
                {
                    "name": "toto-nv",
                    "database_name": "toto-nv",
                    "database_hosting": "saas",
                    "database_url": "http://toto-nv.my.odoo.test",
                    "database_api_login": "contact@toto-nv.be",
                    "database_version": "18.0",
                },
            ],
        )

        self.set_returned_databases_list(
            [
                {
                    "name": "odoo",
                    "login": "other_user@odoo.com",
                    "version": "17.0+e",
                    "url": "http://odoo-sa.my.odoo.test",
                },
            ]
        )
        with self.capture_wizard() as captured:
            Project.action_synchronize_all_databases()
        (wizard,) = captured["wizards"]
        self.assertEqual(wizard.summary_message, "0 new databases, 3 updated.")

        self.assertEqual(Project.search([]), new_projects)
        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "odoo-sa",
                    "database_name": "odoo",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_api_login": "other_user@odoo.com",
                    "database_version": "17.0",
                },
                {
                    "name": "titi-sarl",
                    "database_name": "titi-sarl",
                    "database_hosting": "saas",
                    "database_url": "http://titi-sarl.my.odoo.test",
                    "database_api_login": "admin@titi-sarl.fr",
                    "database_version": "17.0",
                },
                {
                    "name": "toto-nv",
                    "database_name": "toto-nv",
                    "database_hosting": "saas",
                    "database_url": "http://toto-nv.my.odoo.test",
                    "database_api_login": "contact@toto-nv.be",
                    "database_version": "18.0",
                },
            ],
        )

    def test_odoocom_db_synchronization(self):
        Project = self.env["project.project"]
        self.set_returned_databases_list(
            [
                {
                    "name": "cron-odoo-sa",
                    "login": "some_user@odoo.com",
                    "version": "16.0+e",
                    "url": "http://cron-odoo-sa.my.odoo.test",
                },
            ]
        )
        with freeze_time("2025-01-01 00:00"):
            Project._cron_sync_all_databases_with_odoocom()
        new_projects = Project.search([])

        self.assertRecordValues(
            new_projects,
            [
                {
                    "name": "cron-odoo-sa",
                    "database_name": "cron-odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://cron-odoo-sa.my.odoo.test",
                    "database_api_login": "some_user@odoo.com",
                    "database_version": "16.0",
                    "database_last_synchro": False,
                },
            ],
        )

        cron_odoo_sa_xmlrpc_common = MagicMock()
        cron_odoo_sa_xmlrpc_common.version.return_value = {"server_serie": "saas~18.4"}
        self.call_resolution_per_uri[
            "http://cron-odoo-sa.my.odoo.test/xmlrpc/2/common"
        ] = cron_odoo_sa_xmlrpc_common
        with freeze_time("2025-01-01 00:00"):
            Project._cron_sync_all_databases()
        self.assertEqual(
            new_projects.database_last_synchro,
            fields.Datetime.from_string("2025-01-01 00:00"),
            "The database should now have been scanned",
        )

        with freeze_time("2025-01-01 23:59"):
            Project._cron_sync_all_databases()
        self.assertEqual(
            new_projects.database_last_synchro,
            fields.Datetime.from_string("2025-01-01 00:00"),
            "The database shouldn't have been scanned yet",
        )

        with freeze_time("2025-01-02 00:00"):
            Project._cron_sync_all_databases()
        self.assertEqual(
            new_projects.database_last_synchro,
            fields.Datetime.from_string("2025-01-02 00:00"),
            "The database should have been scanned",
        )

    @users("db_manager@company.tld")
    def test_user_management(self):
        database = self.env["project.project"].create(
            [
                {
                    "name": "odoo-sa",
                    "database_hosting": "saas",
                    "database_url": "http://odoo-sa.my.odoo.test",
                    "database_name": "odoo-sa",
                    "database_api_login": "admin",
                    "database_api_key": "admin_apikey",
                }
            ]
        )
        invite_wizard = self.env["wizard.project.project.update.database.user"].create(
            {
                "mode": "invite",
                "database_ids": database.ids,
                "user_ids": self.user_employee.ids,
            }
        )

        invite_wizard.action_invite_users()
        self.assertCountEqual(
            self.odoo_sa_xmrpc_common.authenticate.mock_calls,
            [
                call("odoo-sa", "admin", "admin_apikey", {}),
            ],
        )
        self.assertCountEqual(
            self.odoo_sa_xmrpc_object.execute_kw.mock_calls,
            [
                call(
                    "odoo-sa",
                    -128,
                    "admin_apikey",
                    "res.users",
                    "web_create_users",
                    [],
                    {
                        "emails": ["employee@company.tld"],
                        "context": {"no_reset_password": True},
                    },
                ),
            ],
        )
        self.assertFalse(invite_wizard.error_message)

        self.odoo_sa_xmrpc_common.authenticate.reset_mock()
        self.odoo_sa_xmrpc_object.execute_kw.reset_mock()
        self.odoo_sa_xmrpc_object.execute_kw.side_effect = [[1024], True]
        remove_wizard = self.env["wizard.project.project.update.database.user"].create(
            {
                "mode": "remove",
                "database_ids": database.ids,
                "user_ids": self.user_employee.ids,
            }
        )
        invite_wizard.action_remove_users()
        self.assertCountEqual(
            self.odoo_sa_xmrpc_object.execute_kw.mock_calls,
            [
                call(
                    "odoo-sa",
                    -128,
                    "admin_apikey",
                    "res.users",
                    "search",
                    [
                        [("login", "in", ["employee@company.tld"])],
                    ],
                ),
                call(
                    "odoo-sa",
                    -128,
                    "admin_apikey",
                    "res.users",
                    "write",
                    [
                        [1024],
                        {"active": False},
                    ],
                ),
            ],
        )

        self.assertFalse(remove_wizard.error_message)

import re
import urllib.parse
from collections import defaultdict
from contextlib import contextmanager
from socket import AF_INET, IPPROTO_TCP, SOCK_STREAM
from unittest.mock import MagicMock, patch

from requests.exceptions import ConnectionError as RequestsConnectionError

from odoo import api
from odoo.fields import Domain
from odoo.libs.guarded_http import GuardedSession
from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase


class TestDatabasesCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        pre_existing_project = cls.env["project.project"].search([])
        origin_search_fetch = cls.env.registry["project.project"].search_fetch

        @api.model
        def search_fetch(cls, domain, *args, **kwargs):
            return origin_search_fetch(
                cls,
                Domain.AND([domain, [("id", "not in", pre_existing_project.ids)]]),
                *args,
                **kwargs,
            )

        cls.startClassPatcher(
            patch.object(
                cls.env.registry["project.project"], "search_fetch", search_fetch
            )
        )

        cls.user_employee = new_test_user(
            cls.env, login="employee@company.tld", groups="base.group_user"
        )
        cls.user_db_user = new_test_user(
            cls.env,
            login="db_user@company.tld",
            groups="databases.group_databases_user",
        )
        cls.user_db_manager = new_test_user(
            cls.env,
            login="db_manager@company.tld",
            groups="databases.group_databases_manager",
        )
        cls.user_proj_user = new_test_user(
            cls.env,
            login="project_user@company.tld",
            groups="project.group_project_user",
        )
        cls.user_proj_manager = new_test_user(
            cls.env,
            login="project_manager@company.tld",
            groups="project.group_project_manager",
        )

        cls.env["credential.credential"]._set_system_secret(
            "databases.odoocom_apikey", "privateKey"
        )

        cls.startClassPatcher(
            patch(
                "odoo.addons.databases.wizards.wizard_project_project_synchronize_database.getaddrinfo",
                return_value=[
                    (AF_INET, SOCK_STREAM, IPPROTO_TCP, "", ("127.0.0.1", 0))
                ],
            )
        )

    def setUp(self):
        super().setUp()

        self.json2_mocked_calls = defaultdict(lambda: defaultdict(dict))

        def mock_requests_request(method, uri, *args, **kwargs):
            parsed_url = urllib.parse.urlparse(uri)

            if parsed_url.hostname not in self.json2_mocked_calls:
                raise RequestsConnectionError
            hostname_calls = self.json2_mocked_calls[parsed_url.hostname]

            if parsed_url.path == "/json/version":
                self.assertEqual(method, "get")
                if "version" not in hostname_calls:
                    return MagicMock(status_code=303)
                value = {
                    "version": hostname_calls["version"],
                }
                return MagicMock(status_code=200, **{"json.return_value": value})
            m = re.match(
                r"^/json/2/(?P<model>[^/]*)/(?P<method>[^/]*)$", parsed_url.path
            )
            self.assertTrue(m, f"{uri!r} is not a valid /json/2 route")
            self.assertEqual(method, "post")

            model_name = m.group("model")
            self.assertIn(
                model_name,
                hostname_calls,
                f"No json2_mocked_calls defined for {parsed_url.hostname!r}/{model_name!r}",
            )
            model = hostname_calls[model_name]

            method_name = m.group("method")
            self.assertIn(method_name, model)
            value = model[method_name]

            return MagicMock(status_code=200, **{"json.return_value": value})

        self.mock_requests_request = self.startPatcher(
            patch.object(GuardedSession, "request", side_effect=mock_requests_request)
        )

    @contextmanager
    def capture_wizard(self):
        WizardType = self.env.registry["wizard.project.project.synchronize.database"]
        original_do_sync = WizardType._do_sync
        captured = {"wizards": []}

        def side_effect(self):
            captured["wizards"].append(self)
            return original_do_sync(self)

        with patch.object(
            WizardType, "_do_sync", side_effect=side_effect, autospec=True
        ):
            yield captured

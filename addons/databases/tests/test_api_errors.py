from unittest.mock import patch

import requests

from odoo.libs import guarded_http
from odoo.tests import BaseCase

from ..api import ApiError, OdooDatabaseXmlrpcApi


class TestXmlrpcApiErrors(BaseCase):
    def test_a_transport_failure_is_an_api_error(self):
        api = OdooDatabaseXmlrpcApi("https://db.example.com", "db", "admin", "key")
        for error in (
            requests.ConnectionError("down"),
            requests.Timeout("slow"),
            guarded_http.RefusedDestination("10.0.0.1 is private"),
        ):
            with (
                self.subTest(error=type(error).__name__),
                patch.object(guarded_http.GuardedSession, "post", side_effect=error),
                self.assertRaises(ApiError),
            ):
                api.list_internal_users()

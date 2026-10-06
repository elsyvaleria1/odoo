import base64
import hashlib
import hmac
import json
from unittest.mock import patch

import requests

from odoo.tests.common import TransactionCase

from odoo.addons.account_online_synchronization.models.odoofin_auth import OdooFinAuth


class _Creds:
    access_token = "access-token"
    refresh_token = base64.b64encode(b"secret-key").decode()
    client_id = "client-1"


class TestOdooFinAuth(TransactionCase):
    def _prepared_request(self, url, payload):
        return requests.Request("POST", url, json=payload).prepare()

    def test_unsigned_without_credentials(self):
        """Check that requests stay untouched when no client credentials
        exist."""
        request = self._prepared_request("https://odoofin.test/proxy", {"a": 1})
        signed = OdooFinAuth()(request)
        self.assertNotIn("odoofin-signature", signed.headers)
        self.assertNotIn("odoofin-client-id", signed.headers)

    def test_signature_contract(self):
        """Check the signature headers and recompute the HMAC to pin the
        message layout (timestamp|path|client|token|query|body)."""
        url = "https://odoofin.test/proxy/exchange?b=2&a=1&a=9&empty="
        payload = {"z": 26, "m": 13}
        request = self._prepared_request(url, payload)

        with patch(
            "odoo.addons.account_online_synchronization.models.odoofin_auth.time.time",
            return_value=1_753_000_000,
        ):
            signed = OdooFinAuth(record=_Creds())(request)

        self.assertEqual(signed.headers["odoofin-client-id"], "client-1")
        self.assertEqual(signed.headers["odoofin-access-token"], "access-token")
        self.assertEqual(signed.headers["odoofin-timestamp"], 1_753_000_000)

        # first value wins on repeated keys, blank values kept
        expected_query = json.dumps({"a": "1", "b": "2", "empty": ""}, sort_keys=True)
        expected_message = "1753000000|/proxy/exchange|client-1|access-token|%s|%s" % (
            expected_query,
            json.dumps(payload, sort_keys=True),
        )
        expected_signature = base64.b64encode(
            hmac.new(b"secret-key", expected_message.encode(), hashlib.sha256).digest()
        )
        self.assertEqual(signed.headers["odoofin-signature"], expected_signature)

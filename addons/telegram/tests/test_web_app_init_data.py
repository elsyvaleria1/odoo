import hashlib
import hmac
import time
from urllib.parse import urlencode

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import BaseCase, tagged

from odoo.addons.telegram.tools.web_app import (
    INIT_DATA_MAX_AGE_SECONDS,
    resolve_init_data,
)

TOKEN = "123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


def signed_init_data(token, fields_):
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields_.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields_, "hash": digest})


@tagged("post_install", "-at_install")
class TestInitDataVerification(BaseCase):
    def _fields(self, auth_date):
        return {"auth_date": str(int(auth_date)), "user": json_dumps({"id": 555})}

    def test_fresh_signed_init_data_is_accepted(self):
        parsed = resolve_init_data(
            TOKEN, signed_init_data(TOKEN, self._fields(time.time()))
        )

        self.assertEqual(json_loads(parsed["user"])["id"], 555)

    def test_signed_init_data_older_than_the_window_is_refused(self):
        stale = time.time() - INIT_DATA_MAX_AGE_SECONDS - 1

        self.assertIsNone(
            resolve_init_data(TOKEN, signed_init_data(TOKEN, self._fields(stale)))
        )

    def test_signed_init_data_from_the_future_is_refused(self):
        future = time.time() + 3600

        self.assertIsNone(
            resolve_init_data(TOKEN, signed_init_data(TOKEN, self._fields(future)))
        )

    def test_signed_init_data_without_auth_date_is_refused(self):
        self.assertIsNone(
            resolve_init_data(
                TOKEN, signed_init_data(TOKEN, {"user": json_dumps({"id": 5})})
            )
        )

    def test_a_tampered_hash_is_refused(self):
        fields_ = self._fields(time.time())

        self.assertIsNone(
            resolve_init_data(TOKEN, urlencode({**fields_, "hash": "0" * 64}))
        )

    def test_a_non_ascii_hash_is_refused(self):
        fields_ = self._fields(time.time())

        self.assertIsNone(
            resolve_init_data(TOKEN, urlencode({**fields_, "hash": "é" * 64}))
        )

    def test_another_bots_signature_is_refused(self):
        init_data = signed_init_data("987654321:OTHER", self._fields(time.time()))

        self.assertIsNone(resolve_init_data(TOKEN, init_data))

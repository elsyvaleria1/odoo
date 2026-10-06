from odoo.libs.json import dumps_bytes as json_dumps_bytes

from .sign_request_common import SignRequestCommon
from odoo.addons.base.tests.common import HttpCaseWithUserDemo
from odoo.addons.sign.controllers.main import Sign


class TestSignControllerCommon(SignRequestCommon, HttpCaseWithUserDemo):
    def setUp(self):
        super().setUp()
        self.SignController = Sign()

    def _json_url_open(self, url, data, **kwargs):
        data = {
            "id": 0,
            "jsonrpc": "2.0",
            "method": "call",
            "params": data,
        }
        headers = {"Content-Type": "application/json", **kwargs.get("headers", {})}
        return self.url_open(url, data=json_dumps_bytes(data), headers=headers)

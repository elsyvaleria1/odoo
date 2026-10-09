from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.http import JsonRpcException


@tagged("post_install", "-at_install")
class TestIotChannelAccess(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        new_test_user(
            cls.env,
            login="iot_portal",
            password="iot_portal_pw1",
            groups="base.group_portal",
        )
        new_test_user(
            cls.env,
            login="iot_internal",
            password="iot_internal_pw1",
            groups="base.group_user",
        )
        cls.channel = cls.env["iot.channel"].get_iot_channel()

    def _call(self, model, method, args=()):
        return self.call_jsonrpc(
            "/web/dataset/call_kw",
            {"model": model, "method": method, "args": list(args), "kwargs": {}},
        )

    def test_a_portal_user_is_never_handed_the_channel(self):
        self.authenticate("iot_portal", "iot_portal_pw1")
        self.assertNotIn("iot_channel", self._call("ir.http", "lazy_session_info"))
        with self.assertRaisesRegex(JsonRpcException, "AccessError"):
            self._call("iot.channel", "get_iot_channel", [0])
        with self.assertRaisesRegex(JsonRpcException, "AccessError"):
            self._call("iot.channel", "send_message", [{"iot_identifiers": []}])

    def test_an_internal_user_reaches_the_boxes(self):
        self.authenticate("iot_internal", "iot_internal_pw1")
        self.assertEqual(
            self._call("ir.http", "lazy_session_info")["iot_channel"], self.channel
        )
        self.assertEqual(
            self._call("iot.channel", "get_iot_channel", [0]), self.channel
        )

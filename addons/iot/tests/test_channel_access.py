from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.http import JsonRpcException

from odoo.addons.bus.tools.channel_capability import channel_target, resolve_capability
from odoo.addons.iot.models.iot_channel import BOX_CHANNEL, REPLY_CHANNEL


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
        cls.alice = new_test_user(
            cls.env,
            login="iot_alice",
            password="iot_alice_pw1",
            groups="base.group_user",
        )
        cls.bob = new_test_user(
            cls.env, login="iot_bob", password="iot_bob_pw1", groups="base.group_user"
        )
        cls.box, cls.other_box = (
            cls.env["iot.box"]
            .sudo()
            .create(
                [
                    {"name": "Shop", "identifier": "box_shop", "token": "shop-token"},
                    {"name": "Back", "identifier": "box_back", "token": "back-token"},
                ]
            )
        )

    def setUp(self):
        super().setUp()
        self.sent = []
        patcher = patch.object(
            type(self.env["bus.bus"]),
            "_sendone",
            lambda _bus, target, message_type, message: self.sent.append(
                (target, message_type, message)
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _call(self, model, method, args=()):
        return self.call_jsonrpc(
            "/web/dataset/call_kw",
            {"model": model, "method": method, "args": list(args), "kwargs": {}},
        )

    def _target(self, scope, key):
        return channel_target(self.env, scope, key)

    def test_a_portal_user_is_never_handed_a_channel(self):
        self.authenticate("iot_portal", "iot_portal_pw1")
        self.assertNotIn("iot_channel", self._call("ir.http", "lazy_session_info"))
        with self.assertRaisesRegex(JsonRpcException, "AccessError"):
            self._call("iot.channel", "get_iot_channel", [0])
        with self.assertRaisesRegex(JsonRpcException, "AccessError"):
            self._call(
                "iot.channel", "send_message", [{"iot_identifiers": ["box_shop"]}]
            )
        self.assertEqual(self.sent, [])

    def test_each_user_hears_on_a_channel_of_their_own(self):
        self.authenticate("iot_alice", "iot_alice_pw1")
        alice = self._call("ir.http", "lazy_session_info")["iot_channel"]
        self.assertEqual(self._call("iot.channel", "get_iot_channel", [0]), alice)
        self.authenticate("iot_bob", "iot_bob_pw1")
        bob = self._call("iot.channel", "get_iot_channel", [0])
        self.assertNotEqual(alice, bob)
        self.assertEqual(
            resolve_capability(self.env, alice),
            self._target(REPLY_CHANNEL, f"user.{self.alice.id}"),
        )

    def test_a_request_reaches_only_its_box_and_its_answer_only_its_sender(self):
        self.authenticate("iot_alice", "iot_alice_pw1")
        self._call(
            "iot.channel",
            "send_message",
            [{"iot_identifiers": ["box_shop"], "session_id": "s-1", "action": "print"}],
        )
        channels = self.env["iot.channel"]
        [(target, message_type, request)] = self.sent
        self.assertEqual(target, self._target(BOX_CHANNEL, channels._box_key(self.box)))
        self.assertEqual(message_type, "iot_action")
        self.assertNotEqual(request["session_id"], "s-1", "routed through the box")

        self.sent.clear()
        self.call_jsonrpc(
            "/iot/box/send_websocket",
            {
                "session_id": request["session_id"],
                "iot_box_identifier": "box_shop",
                "device_identifier": "box_shop",
                "status": "success",
            },
        )
        [(target, message_type, answer)] = self.sent
        self.assertEqual(target, self._target(REPLY_CHANNEL, f"user.{self.alice.id}"))
        self.assertEqual(message_type, "operation_confirmation")
        self.assertEqual(answer["session_id"], "s-1")

    def test_an_answer_without_a_valid_route_reaches_nobody(self):
        channels = self.env["iot.channel"]
        forged = channels._wrap_session_id(f"user.{self.alice.id}", "s-1").replace(
            f"user.{self.alice.id}", f"user.{self.bob.id}"
        )
        for session_id in ("s-1", forged, "", None):
            with self.subTest(session_id=session_id):
                self.call_jsonrpc(
                    "/iot/box/send_websocket",
                    {
                        "session_id": session_id,
                        "iot_box_identifier": "box_shop",
                        "device_identifier": "box_shop",
                        "status": "success",
                    },
                )
                self.call_jsonrpc(
                    "/iot/box/webrtc_answer",
                    {
                        "session_id": session_id,
                        "iot_box_identifier": "box_shop",
                        "answer": {},
                    },
                )
        self.assertEqual(self.sent, [])

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
        new_test_user(
            cls.env,
            login="iot_admin",
            password="iot_admin_pw1",
            groups="base.group_user,iot.group_iot_admin",
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
        forged = channels._wrap_session_id(
            f"user.{self.alice.id}", "s-1", "box_shop"
        ).replace(f"user.{self.alice.id}", f"user.{self.bob.id}")
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

    def test_a_user_sends_a_box_only_what_a_web_client_may(self):
        self.authenticate("iot_alice", "iot_alice_pw1")
        for message_type in ("remote_debug", "server_update", "server_clear"):
            with (
                self.subTest(message_type=message_type),
                self.assertRaisesRegex(JsonRpcException, "AccessError"),
            ):
                self._call(
                    "iot.channel",
                    "send_message",
                    [{"iot_identifiers": ["box_shop"], "token": "x"}, message_type],
                )
        self.assertEqual(self.sent, [])
        self._call(
            "iot.channel",
            "send_message",
            [{"iot_identifiers": ["box_shop"], "session_id": "t"}, "test_connection"],
        )
        self.authenticate("iot_admin", "iot_admin_pw1")
        self._call(
            "iot.channel",
            "send_message",
            [{"iot_identifiers": ["box_shop"], "status": True}, "remote_debug"],
        )
        self.assertEqual(
            [message_type for _target, message_type, _message in self.sent],
            ["test_connection", "remote_debug"],
        )

    def test_a_route_returns_only_through_the_box_it_was_sent_to(self):
        self.authenticate("iot_alice", "iot_alice_pw1")
        self._call(
            "iot.channel",
            "send_message",
            [{"iot_identifiers": ["box_shop"], "session_id": "s-1"}],
        )
        [(_target, _type, request)] = self.sent
        self.sent.clear()
        answer = {
            "session_id": request["session_id"],
            "device_identifier": None,
            "status": "success",
        }
        self.call_jsonrpc(
            "/iot/box/send_websocket", {**answer, "iot_box_identifier": "box_back"}
        )
        self.assertEqual(self.sent, [], "replayed through another box")
        self.call_jsonrpc(
            "/iot/box/send_websocket", {**answer, "iot_box_identifier": "box_shop"}
        )
        self.assertEqual(len(self.sent), 1)

    def test_an_upstream_box_answers_its_last_requester_without_a_route(self):
        # upstream's iot_drivers answers an offer with no session id and its
        # remote debug status with session 0
        def offer(login, password):
            self.authenticate(login, password)
            self._call(
                "iot.channel",
                "send_message",
                [{"iot_identifiers": ["box_shop"], "offer": {}}, "webrtc_offer"],
            )

        def answer():
            self.sent.clear()
            self.call_jsonrpc(
                "/iot/box/webrtc_answer",
                {"iot_box_identifier": "box_shop", "answer": {}},
            )
            return [target for target, _type, _message in self.sent]

        offer("iot_alice", "iot_alice_pw1")
        self.assertEqual(
            answer(), [self._target(REPLY_CHANNEL, f"user.{self.alice.id}")]
        )
        offer("iot_bob", "iot_bob_pw1")
        self.assertEqual(answer(), [self._target(REPLY_CHANNEL, f"user.{self.bob.id}")])

        admin = self.env["res.users"].search([("login", "=", "iot_admin")])
        self.authenticate("iot_admin", "iot_admin_pw1")
        self._call(
            "iot.channel",
            "send_message",
            [{"iot_identifiers": ["box_shop"], "status": True}, "remote_debug"],
        )
        self.sent.clear()
        self.call_jsonrpc(
            "/iot/box/send_websocket",
            {
                "session_id": 0,
                "iot_box_identifier": "box_shop",
                "device_identifier": None,
                "status": "success",
                "result": {"enabled": False},
            },
        )
        self.assertEqual(
            [target for target, _type, _message in self.sent],
            [self._target(REPLY_CHANNEL, f"user.{admin.id}")],
        )

        self.sent.clear()
        self.env["iot.device"].sudo().create(
            {"iot_id": self.box.id, "name": "Scanner", "identifier": "scanner_1"}
        )
        self.call_jsonrpc(
            "/iot/box/send_websocket",
            {
                "session_id": None,
                "iot_box_identifier": "box_shop",
                "device_identifier": "scanner_1",
                "status": "success",
            },
        )
        self.assertEqual(self.sent, [], "a device event nobody asked for")

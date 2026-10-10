from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, new_test_user, tagged

from ..tools.channel_capability import (
    channel_capability,
    channel_target,
    register_channel_scope,
    resolve_capability,
)
from .common import TEST_CHANNEL as TEST_SCOPE
from .common import WebsocketCase

HELD_CHANNEL = register_channel_scope(
    "bus_test_held",
    purpose="tests: a channel only the user its key names may hold",
    lifetime="undated",
    holder=lambda env, key: key == str(env.uid),
)


@tagged("-at_install", "post_install")
class TestChannelCapability(TransactionCase):
    def test_a_capability_resolves_to_its_target(self):
        name = channel_capability(self.env, TEST_SCOPE, "42")
        self.assertTrue(name.startswith("bus:bus_test:42:"))
        self.assertEqual(
            resolve_capability(self.env, name), channel_target(self.env, TEST_SCOPE, 42)
        )

    def test_a_forged_or_foreign_name_resolves_to_nothing(self):
        name = channel_capability(self.env, TEST_SCOPE, "42")
        signature = name.rpartition(":")[2]
        for forged in (
            f"bus:bus_test:43:{signature}",
            f"bus:bus_test:42:{'0' * len(signature)}",
            f"bus:unknown_scope:42:{signature}",
            "bus:bus_test:42",
            "bus_test:42",
            "broadcast",
            "",
        ):
            with self.subTest(forged=forged):
                self.assertIsNone(resolve_capability(self.env, forged))

    def test_a_key_cannot_carry_the_separator(self):
        with self.assertRaises(ValueError):
            channel_capability(self.env, TEST_SCOPE, "4:2")
        with self.assertRaises(ValueError):
            channel_target(self.env, "unregistered", "42")

    def test_a_held_capability_resolves_only_for_the_holder_it_names(self):
        alice = new_test_user(self.env, login="held_alice", groups="base.group_user")
        bob = new_test_user(self.env, login="held_bob", groups="base.group_user")
        name = channel_capability(self.env, HELD_CHANNEL, str(alice.id))
        target = channel_target(self.env, HELD_CHANNEL, str(alice.id))
        self.assertEqual(resolve_capability(self.env(user=alice), name), target)
        self.assertIsNone(resolve_capability(self.env(user=bob), name))
        public = self.env.ref("base.public_user")
        for user, expected in ((alice, {target}), (bob, set()), (public, set())):
            with self.subTest(user=user.login):
                channels = (
                    self.env["ir.websocket"]
                    .with_user(user)
                    ._prepare_subscribe_data([name], 0)["channels"]
                )
                self.assertEqual(set(channels) & {target}, expected)


@tagged("-at_install", "post_install")
class TestChannelCapabilitySubscription(WebsocketCase):
    def _receives(self, name):
        websocket = self.websocket_connect()
        self.subscribe(websocket, [name], self.env["bus.bus"]._bus_last_id())
        target = channel_target(self.env, TEST_SCOPE, "7")
        self.env["bus.bus"]._sendone(target, "capability_probe", {"n": 1})
        self.trigger_notification_dispatching([target])
        websocket.settimeout(0.5)
        try:
            return [n["message"]["type"] for n in json_loads(websocket.recv())]
        except TimeoutError:
            return []
        except Exception as exc:
            if type(exc).__name__ == "WebSocketTimeoutException":
                return []
            raise

    def test_the_holder_of_a_capability_receives_its_channel(self):
        name = channel_capability(self.env, TEST_SCOPE, "7")
        self.assertEqual(self._receives(name), ["capability_probe"])

    def test_a_forged_capability_receives_nothing(self):
        name = channel_capability(self.env, TEST_SCOPE, "7")
        forged = name[:-4] + "0000"
        self.assertEqual(self._receives(forged), [])
        self.assertEqual(self._receives("7"), [])

from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, tagged

from ..tools.channel_capability import (
    channel_capability,
    channel_target,
    register_channel_scope,
    resolve_capability,
)
from .common import WebsocketCase

TEST_SCOPE = register_channel_scope(
    "bus_test",
    purpose="tests of the bus channel capabilities",
    lifetime="undated: test channels",
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

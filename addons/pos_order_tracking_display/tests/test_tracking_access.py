import re
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.bus.tools.channel_capability import channel_target, resolve_capability
from odoo.addons.point_of_sale.models.mixin_pos_bus import POS_CHANNEL


@tagged("post_install", "-at_install")
class TestOrderTrackingAccess(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.display = cls.env["pos.prep.display"].create({"name": "Kitchen Display"})

    def _target(self, audience):
        return channel_target(
            self.env, POS_CHANNEL, self.display._pos_bus_key(audience)
        )

    def test_the_tracking_screen_opens_with_its_own_token_only(self):
        kitchen_token = self.display.access_token
        refused = self.url_open(f"/pos-order-tracking/?access_token={kitchen_token}")
        self.assertEqual(refused.status_code, 404)
        for forged in ("", f"{self.display.id}-0000", "abc-def"):
            with self.subTest(forged=forged):
                response = self.url_open(f"/pos-order-tracking/?access_token={forged}")
                self.assertEqual(response.status_code, 404)

        page = self.url_open(
            f"/pos-order-tracking/?access_token={self.display._tracking_token()}"
        )
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(kitchen_token, page.text)
        channel = re.search(r'"bus_channel": "([^"]+)"', page.text)
        self.assertTrue(channel, "the tracking screen is handed its own channel")
        self.assertEqual(
            resolve_capability(self.env, channel.group(1)),
            self._target("order_tracking"),
        )

    def test_revoking_the_tracking_link_stops_the_open_screen_and_its_old_link(self):
        old_token = self.display._tracking_token()
        old_tracking = self._target("order_tracking")
        kitchen = self._target("till")
        sent = []
        with patch.object(
            type(self.env["bus.bus"]),
            "_sendone",
            lambda _bus, target, message_type, _message: sent.append(
                (target, message_type.rpartition("-")[2])
            ),
        ):
            self.display.action_revoke_tracking_link()
        self.assertEqual(sent, [(old_tracking, "LINK_REVOKED")])
        self.assertEqual(self._target("till"), kitchen, "the kitchen hears on")
        new_token = self.display._tracking_token()
        self.assertNotEqual(new_token, old_token)
        for token, status in ((old_token, 404), (new_token, 200)):
            with self.subTest(status=status):
                page = self.url_open(f"/pos-order-tracking/?access_token={token}")
                self.assertEqual(page.status_code, status)

    def test_the_tracking_screen_hears_order_numbers_and_nothing_else(self):
        sent = []
        with patch.object(
            type(self.env["bus.bus"]),
            "_sendone",
            lambda _bus, target, message_type, _message: sent.append(
                (target, message_type.rpartition("-")[2])
            ),
        ):
            self.display._send_load_orders_message(notification="Table 4 is angry")
            self.display._send_notification(notification="Out of fries")
        tracking = [
            name for target, name in sent if target == self._target("order_tracking")
        ]
        kitchen = [name for target, name in sent if target == self._target("till")]
        self.assertEqual(tracking, ["NEW_ORDERS"])
        self.assertEqual(kitchen, ["LOAD_ORDERS", "NOTIFICATION"])

    def test_the_open_tracking_screen_hears_new_orders_over_the_bus(self):
        code = """
            (async () => {
                const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const shows = (text) => document.body.innerText.includes(text);
                await wait(2000);
                await fetch("/web/dataset/call_kw/pos.prep.state/change_state_stage", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: {
                            model: "pos.prep.state",
                            method: "change_state_stage",
                            args: [[], {}, %(display)s],
                            kwargs: {},
                        },
                    }),
                });
                for (let i = 0; i < 100 && !shows("7031"); i++) {
                    await wait(100);
                }
                if (shows("7031")) {
                    console.log("test successful");
                } else {
                    console.error("the new order never reached the tracking screen");
                }
            })();
        """ % {"display": self.display.id}
        Display = type(self.display)
        send = Display._send_orders_to_customer_display
        notifying = []

        def get_pos_orders(_display):
            # only what is sent can show the order: the page render gets none
            pending = ["7031"] if notifying else []
            return {"done": [], "notDone": pending, "ordersCompletedReadyDate": {}}

        def send_orders(display):
            notifying.append(True)
            try:
                return send(display)
            finally:
                notifying.pop()

        with (
            patch.object(Display, "_get_pos_orders", get_pos_orders),
            patch.object(Display, "_send_orders_to_customer_display", send_orders),
        ):
            self.browser_js(
                f"/pos-order-tracking/?access_token={self.display._tracking_token()}",
                code,
                login="admin",
                timeout=60,
            )

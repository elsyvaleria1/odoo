from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged
from odoo.tests.http import JsonRpcException

from odoo.addons.bus.tools.channel_capability import channel_target, resolve_capability
from odoo.addons.point_of_sale.models.mixin_pos_bus import POS_CHANNEL
from odoo.addons.pos_self_order.models.pos_config import SELF_ORDER_CHANNEL
from odoo.addons.pos_self_order.models.pos_order import ORDER_CHANNEL
from odoo.addons.pos_self_order.tests.self_order_common_test import SelfOrderCommonTest


@tagged("post_install", "-at_install")
class TestSelfOrderChannels(SelfOrderCommonTest):
    def setUp(self):
        super().setUp()
        self.pos_config.write(
            {
                "self_ordering_mode": "kiosk",
                "self_ordering_pay_after": "each",
                "self_ordering_service_mode": "counter",
            }
        )
        self.pos_config.with_user(self.pos_user).open_ui()
        self.pos_config.current_session_id.set_opening_control(0, "")
        self.sent = []
        Bus = type(self.env["bus.bus"])
        sendone = Bus._sendone

        def record(bus, target, notification_type, message):
            self.sent.append((target, notification_type, repr(message)))
            return sendone(bus, target, notification_type, message)

        patcher = patch.object(Bus, "_sendone", record)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _order(self):
        order = self.env["pos.order"].create(
            {
                "session_id": self.pos_config.current_session_id.id,
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
                "lines": [
                    Command.create(
                        {
                            "product_id": self.cola.id,
                            "qty": 1,
                            "price_unit": 10,
                            "price_subtotal": 10,
                            "price_subtotal_incl": 10,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        order._recompute_amounts()
        return order

    def test_the_qr_code_does_not_carry_the_tills_channel(self):
        till_token = self.pos_config.access_token
        self_token = self.pos_config.self_ordering_access_token

        route = self.pos_config._get_self_order_route()
        loaded = self.pos_config.load_self_data()["pos.config"][0]

        self.assertNotEqual(self_token, till_token)
        self.assertIn(self_token, route)
        self.assertNotIn(till_token, route)
        self.assertEqual(loaded["access_token"], self_token)
        self.assertNotIn("customer_display_token", loaded)

    def test_the_tills_token_opens_no_self_order(self):
        with self.assertRaises(JsonRpcException):
            self.call_jsonrpc(
                "/pos-self/ping", {"access_token": self.pos_config.access_token}
            )
        pong = self.call_jsonrpc(
            "/pos-self/ping",
            {"access_token": self.pos_config.self_ordering_access_token},
        )
        self.assertEqual(pong, {"response": "pong"})

    def test_a_payment_result_goes_to_the_orders_own_channel(self):
        order = self._order()

        order._send_payment_result("fail")

        target = channel_target(self.env, ORDER_CHANNEL, order._self_order_bus_key())
        self.assertEqual({target for target, _, _ in self.sent}, {target})
        self.assertEqual(resolve_capability(self.env, order.self_order_channel), target)
        self.assertNotIn(order.access_token, order.self_order_channel)
        self.assertNotIn(
            self.pos_config.self_ordering_access_token, order.self_order_channel
        )

    def test_the_public_channel_carries_no_order_token(self):
        order = self._order()
        self.env["pos.order"]._notify_order_state_changed(order)
        order._send_payment_result("fail")

        public = [
            message
            for target, _, message in self.sent
            if target
            == channel_target(
                self.env, SELF_ORDER_CHANNEL, self.pos_config._self_order_bus_key()
            )
        ]
        self.assertTrue(public)
        for message in public:
            self.assertNotIn(order.access_token, message)
        till = channel_target(
            self.env, POS_CHANNEL, self.pos_config._pos_bus_key("till")
        )
        self.assertNotIn(till, [target for target, _, _ in self.sent])

    def test_a_product_change_tells_each_kiosk_once_whichever_door_it_came_by(self):
        size = self.env["product.attribute"].create(
            {
                "name": "Size",
                "value_ids": [
                    Command.create({"name": "S"}),
                    Command.create({"name": "L"}),
                ],
            }
        )
        sized = self.env["product.template"].create(
            {
                "name": "Sized",
                "available_in_pos": True,
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": size.id,
                            "value_ids": [Command.set(size.value_ids.ids)],
                        }
                    )
                ],
            }
        )
        self.assertEqual(len(sized.product_variant_ids), 2)
        public = channel_target(
            self.env, SELF_ORDER_CHANNEL, self.pos_config._self_order_bus_key()
        )

        def changes():
            sent = [
                name
                for target, name, _ in self.sent
                if target == public and name.endswith("-PRODUCT_CHANGED")
            ]
            self.sent.clear()
            return len(sent)

        self.sent.clear()
        self.cola.write({"self_order_available": False})
        self.assertEqual(changes(), 1, "a variant's write")
        sized.write({"self_order_available": False})
        self.assertEqual(changes(), 1, "a template of two variants")


@tagged("post_install", "-at_install")
class TestSelfOrderLive(SelfOrderCommonTest):
    def setUp(self):
        super().setUp()
        self.pos_config.write(
            {
                "self_ordering_mode": "kiosk",
                "self_ordering_pay_after": "each",
                "self_ordering_service_mode": "counter",
            }
        )
        self.pos_config.with_user(self.pos_user).open_ui()
        self.pos_config.current_session_id.set_opening_control(0, "")

    def test_an_open_kiosk_hears_a_product_made_available_over_the_bus(self):
        product = self.env["product.product"].create(
            {
                "name": "Live bus probe",
                "list_price": 1,
                "taxes_id": False,
                "available_in_pos": True,
                "self_order_available": False,
                "pos_categ_ids": self.cola.pos_categ_ids.ids,
            }
        )
        code = """
            (async () => {
                const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const until = async (predicate) => {
                    for (let i = 0; i < 150 && !predicate(); i++) {
                        await wait(100);
                    }
                    return predicate();
                };
                const selfOrder = () => window.posmodel;
                const offers = () =>
                    selfOrder()?.models["product.template"].some(
                        (template) => template.name === "Live bus probe",
                    );
                if (!(await until(() => selfOrder()?.models))) {
                    console.error("the kiosk never loaded");
                    return;
                }
                if (offers()) {
                    console.error("the product was offered before it was made available");
                    return;
                }
                await wait(1500);
                await fetch("/web/dataset/call_kw/product.product/write", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: {
                            model: "product.product",
                            method: "write",
                            args: [[%(product)s], { self_order_available: true }],
                            kwargs: {},
                        },
                    }),
                });
                if (await until(offers)) {
                    console.log("test successful");
                } else {
                    console.error("the product never reached the open kiosk");
                }
            })();
        """ % {"product": product.id}
        self.browser_js(
            self.pos_config._get_self_order_route(), code, login="admin", timeout=60
        )

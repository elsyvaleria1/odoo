from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.libs.json import loads as json_loads

try:
    import websocket as ws
except ImportError:
    ws = None

from odoo.tests import new_test_user, tagged

from odoo.addons.bus.models.bus import channel_with_db, json_dump
from odoo.addons.bus.tests.common import WebsocketCase
from odoo.addons.bus.websocket import CloseCode
from odoo.addons.mail.models.mail_presence import AWAY_TIMER


@tagged("-at_install", "post_install")
class TestIrWebsocket(WebsocketCase):
    def test_notify_on_status_change(self):
        bob = new_test_user(self.env, login="bob_user", groups="base.group_user")
        session = self.authenticate("bob_user", "bob_user")
        websocket = self.websocket_connect(cookie=f"session_id={session.sid};")
        self.subscribe(
            websocket,
            [f"odoo-presence-res.partner_{bob.partner_id.id}"],
            self.env["bus.bus"]._bus_last_id(),
        )
        self.env["mail.presence"]._update_presence(bob)
        self.trigger_notification_dispatching([(bob.partner_id, "presence")])
        message = json_loads(websocket.recv())[0]["message"]
        self.assertEqual(message["type"], "mail.presence/im_status_updated")
        self.assertEqual(message["payload"]["im_status"], "online")
        self.assertEqual(message["payload"]["presence_status"], "online")
        self.assertEqual(message["payload"]["partner_id"], bob.partner_id.id)
        away_timer_later = datetime.now() + timedelta(seconds=AWAY_TIMER + 1)
        with freeze_time(away_timer_later):
            self.env["mail.presence"]._update_presence(bob, (AWAY_TIMER + 1) * 1000)
            self.trigger_notification_dispatching([(bob.partner_id, "presence")])
            message = json_loads(websocket.recv())[0]["message"]
            self.assertEqual(message["type"], "mail.presence/im_status_updated")
            self.assertEqual(message["payload"]["im_status"], "away")
            self.assertEqual(message["payload"]["presence_status"], "away")
            self.assertEqual(message["payload"]["partner_id"], bob.partner_id.id)
        ten_minutes_later = datetime.now() + timedelta(minutes=10)
        with freeze_time(ten_minutes_later):
            self.env["mail.presence"]._update_presence(bob)
            self.trigger_notification_dispatching([(bob.partner_id, "presence")])
            message = json_loads(websocket.recv())[0]["message"]
            self.assertEqual(message["type"], "mail.presence/im_status_updated")
            self.assertEqual(message["payload"]["im_status"], "online")
            self.assertEqual(message["payload"]["presence_status"], "online")
            self.assertEqual(message["payload"]["partner_id"], bob.partner_id.id)
        ten_minutes_later = datetime.now() + timedelta(minutes=10)
        with freeze_time(ten_minutes_later):
            self.env["mail.presence"]._update_presence(bob)
            self.trigger_notification_dispatching([(bob.partner_id, "presence")])
            timeout_occurred = False
            websocket.settimeout(1)
            try:
                websocket.recv()
            except ws._exceptions.WebSocketTimeoutException:
                timeout_occurred = True
            self.assertTrue(timeout_occurred)

    def test_receive_missed_presences_on_subscribe(self):
        bob = new_test_user(self.env, login="bob_user", groups="base.group_user")
        session = self.authenticate("bob_user", "bob_user")
        websocket = self.websocket_connect(cookie=f"session_id={session.sid};")
        self.env["mail.presence"]._update_presence(bob)
        self.env.cr.precommit.run()
        self.subscribe(
            websocket,
            [f"odoo-presence-res.partner_{bob.partner_id.id}"],
            self.env["bus.bus"]._bus_last_id(),
        )
        self.trigger_notification_dispatching([(bob.partner_id, "presence")])
        notification = json_loads(websocket.recv())[0]
        self._close_websockets()
        bus_record = self.env["bus.bus"].search([("id", "=", int(notification["id"]))])
        self.assertEqual(
            bus_record.channel,
            json_dump(channel_with_db(self.env.cr.dbname, bob.partner_id)),
        )
        self.assertEqual(
            notification["message"]["type"], "mail.presence/im_status_updated"
        )
        self.assertEqual(notification["message"]["payload"]["im_status"], "online")
        self.assertEqual(
            notification["message"]["payload"]["presence_status"], "online"
        )
        self.assertEqual(
            notification["message"]["payload"]["partner_id"], bob.partner_id.id
        )

    def test_receive_others_missed_presences_on_subscribe(self):
        bob = new_test_user(self.env, login="bob_user", groups="base.group_user")
        away_user = new_test_user(self.env, login="idler", groups="base.group_user")
        session = self.authenticate("bob_user", "bob_user")
        websocket = self.websocket_connect(cookie=f"session_id={session.sid};")
        self.env["mail.presence"]._update_presence(away_user, (AWAY_TIMER + 1) * 1000)
        self.env.cr.precommit.run()
        self.subscribe(
            websocket,
            [f"odoo-presence-res.partner_{away_user.partner_id.id}"],
            self.env["bus.bus"]._bus_last_id(),
        )
        self.trigger_notification_dispatching([(away_user.partner_id, "presence")])
        notification = json_loads(websocket.recv())[0]
        self._close_websockets()
        bus_record = self.env["bus.bus"].search([("id", "=", int(notification["id"]))])
        self.assertEqual(
            bus_record.channel,
            json_dump(channel_with_db(self.env.cr.dbname, bob.partner_id)),
        )
        self.assertEqual(
            notification["message"]["type"], "mail.presence/im_status_updated"
        )
        self.assertEqual(notification["message"]["payload"]["im_status"], "away")
        self.assertEqual(notification["message"]["payload"]["presence_status"], "away")
        self.assertEqual(
            notification["message"]["payload"]["partner_id"], away_user.partner_id.id
        )

    def test_a_closed_websocket_sets_its_user_offline(self):
        bob = new_test_user(self.env, login="bob_user", groups="base.group_user")
        session = self.authenticate("bob_user", "bob_user")
        self.env["mail.presence"]._update_presence(bob)
        presence = self.env["mail.presence"].search([("user_id", "=", bob.id)])
        self.assertEqual(presence.status, "online")
        websocket = self.websocket_connect(cookie=f"session_id={session.sid};")
        websocket.close(CloseCode.CLEAN)
        self.wait_remaining_websocket_connections()
        presence.invalidate_recordset(["status"])
        self.assertEqual(presence.status, "offline")

    def test_a_backend_page_hears_its_user_and_its_channels_over_the_bus(self):
        john = new_test_user(self.env, login="bus_live_john", groups="base.group_user")
        channel = (
            self.env["discuss.channel"]
            .with_user(john)
            ._create_group(partners_to=john.partner_id.ids)
        )
        code = """
            (async () => {
                const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const until = async (predicate) => {
                    for (let i = 0; i < 100 && !predicate(); i++) {
                        await wait(100);
                    }
                    return predicate();
                };
                const appContext = () =>
                    odoo.__WOWL_DEBUG__?.root &&
                    odoo.loader.modules
                        .get("@web/core/app_context")
                        .appContextOf(odoo.__WOWL_DEBUG__.root);
                await until(() => appContext()?.services?.bus_service);
                const { bus_service: bus, orm } = appContext().services;
                if (!(await until(() => bus.workerState === "CONNECTED"))) {
                    console.error(`the bus never connected: ${bus.workerState}`);
                    return;
                }
                const heard = new Set();
                bus.subscribe("discuss.channel/new_message", (payload) => {
                    if (JSON.stringify(payload).includes("Live bus probe")) {
                        heard.add("channel");
                    }
                });
                bus.subscribe("res.users.settings", (payload) => {
                    if (JSON.stringify(payload).includes("Live bus probe")) {
                        heard.add("user");
                    }
                });
                await orm.call("res.users.settings", "set_res_users_settings", [
                    [%(settings)s],
                    { push_to_talk_key: "Live bus probe" },
                ]);
                await fetch("/mail/message/post", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: {
                            thread_model: "discuss.channel",
                            thread_id: %(channel)s,
                            post_data: { body: "Live bus probe", message_type: "comment" },
                        },
                    }),
                });
                if (await until(() => heard.size === 2)) {
                    console.log("test successful");
                } else {
                    console.error(`heard only ${[...heard]} over the bus`);
                }
            })();
        """ % {
            "settings": self.env["res.users.settings"]._get_or_create_for_user(john).id,
            "channel": channel.id,
        }
        self.browser_js("/odoo", code, login="bus_live_john", timeout=60)

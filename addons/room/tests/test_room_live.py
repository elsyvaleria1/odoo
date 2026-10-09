from odoo.tests import tagged

from odoo.addons.bus.tests.common import WebsocketCase
from odoo.addons.room.tests.common import RoomCommon


@tagged("post_install", "-at_install")
class TestRoomKioskLive(RoomCommon, WebsocketCase):
    def test_a_booking_made_elsewhere_reaches_the_open_kiosk_over_the_bus(self):
        resource = self.resources[0]
        token = resource.access_token
        # a fresh browser subscribes from zero and is replayed the bus's last
        # minute, the setup's kiosk "reload" included, which would navigate away
        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()
        code = """
            (async () => {
                const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const utc = (date) => date.toISOString().slice(0, 19).replace("T", " ");
                await wait(2000);
                const now = Date.now();
                await fetch("/room/%(token)s/booking/create", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: {
                            name: "Live bus probe",
                            start_datetime: utc(new Date(now - 60000)),
                            stop_datetime: utc(new Date(now + 1800000)),
                        },
                    }),
                });
                for (let i = 0; i < 100; i++) {
                    if (document.body.innerText.includes("Live bus probe")) {
                        console.log("test successful");
                        return;
                    }
                    await wait(100);
                }
                console.error("the booking never reached the kiosk over the bus");
            })();
        """ % {"token": token}
        self.browser_js(f"/room/{resource.short_code}/book", code, timeout=60)

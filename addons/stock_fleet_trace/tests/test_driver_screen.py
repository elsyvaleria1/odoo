import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, TransactionCase, tagged

from .common import TripFixtureMixin

HASH_CHECK = Path(__file__).parent / "js" / "hash_check.mjs"
TEST_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY"
    "42YAAAAASUVORK5CYII="
)


def _sample(uuid, **vals):
    return {
        "client_uuid": uuid,
        "event_type": "deliver",
        "picking_id": 7,
        "payload": {},
        "captured_at": "2026-09-29T09:30:00-06:00",
        "latitude": 20.6597,
        "longitude": -103.3496,
        "device_uuid": "phone-1",
        "prev_hash": "",
        **vals,
    }


@tagged("post_install", "-at_install")
class TestDriverHash(TransactionCase):
    """The phone's JavaScript hash equals the server's, byte for byte."""

    def test_the_phone_hash_matches_the_server_hash(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        samples = [
            _sample("a", prev_hash=None, payload=None),
            _sample(
                "b",
                payload={
                    "receiver_name": "José Muñoz Peña — Ñandú ü € 😀",
                    "signature": TEST_PNG_B64,
                },
                prev_hash="0" * 64,
            ),
            _sample(
                "c",
                event_type="not_delivered",
                payload={"reason_id": 3, "note": 'Portón "cerrado"\n\t\\ \x01  '},
                latitude=-0.00001234,
                longitude=1.0,
            ),
            _sample(
                "d",
                event_type="incident",
                picking_id=False,
                latitude=None,
                longitude=None,
                payload={
                    "incident": {
                        "incident_type": "spill",
                        "description": "Bulto roto",
                        "odometer": 123456.7,
                        "fuel_liters": 0.1 + 0.2,
                        "lines": [
                            {"product_id": 1, "quantity": 2.5, "trace_id": None},
                            {"quantity": 1e-7, "product_id": 2},
                        ],
                    }
                },
            ),
            _sample(
                "e",
                event_type="scan",
                payload={
                    "code": "L-001",
                    "quantity": 1,
                    "z": [1e16, 1e21, -5e-05, 123456789.123, 0.0001, -0.0],
                    "é": 1,
                    "😀": 2,
                    "￿": 3,
                    "B": {"b": True, "a": False},
                },
            ),
        ]
        run = subprocess.run(
            [node, str(HASH_CHECK)],
            input=json_dumps_bytes(samples),
            capture_output=True,
            check=True,
            timeout=60,
        )
        results = json_loads(run.stdout)
        Event = self.env["stock.trip.offline.event"]
        self.assertEqual(len(results), len(samples))
        for sample, result in zip(samples, results, strict=True):
            with self.subTest(event=sample["client_uuid"]):
                wire = json_loads(result["wire"])
                self.assertEqual(result["hash"], Event._trip_hash_event(wire))


@tagged("post_install", "-at_install")
class TestDriverScreen(TripFixtureMixin, HttpCase):
    def _rpc(self, url, **params):
        response = self.url_open(url, json=self.prepare_rpc_payload(params))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("error", body, body.get("error"))
        return body["result"]

    def test_the_driver_screen_boots_as_an_installable_app(self):
        self.authenticate("drv_driver", "drv_driver")

        page = self.url_open("/stock_fleet_trace/driver?trip=1")
        manifest = self.url_open("/stock_fleet_trace/driver/manifest.webmanifest")
        worker = self.url_open("/stock_fleet_trace/driver/sw.js")
        script = self.url_open("/stock_fleet_trace/static/driver/app.js")

        self.assertEqual(page.status_code, 200)
        self.assertIn('id="sft-app"', page.text)
        self.assertIn("data-boot=", page.text)
        self.assertIn("/stock_fleet_trace/driver/manifest.webmanifest", page.text)
        self.assertIn(
            '"scan_lot_not_on_board"',
            page.text.replace("&#34;", '"').replace("&quot;", '"'),
        )
        self.assertEqual(manifest.status_code, 200)
        manifest_data = manifest.json()
        self.assertEqual(manifest_data["start_url"], "/stock_fleet_trace/driver")
        self.assertEqual(manifest_data["scope"], "/stock_fleet_trace/driver")
        self.assertEqual(manifest_data["display"], "standalone")
        self.assertEqual(worker.status_code, 200)
        self.assertEqual(
            worker.headers["Service-Worker-Allowed"], "/stock_fleet_trace/driver"
        )
        self.assertIn("javascript", worker.headers["Content-Type"])
        self.assertNotIn("__SFT_DRIVER_VERSION__", worker.text)
        self.assertEqual(script.status_code, 200)

    def test_the_driver_screen_asks_for_a_login(self):
        page = self.url_open("/stock_fleet_trace/driver", allow_redirects=False)

        self.assertIn(page.status_code, (302, 303))
        self.assertIn("/web/login", page.headers["Location"])

    def test_the_driver_sees_the_trips_he_drives(self):
        mine = self._trip(self._delivery(5))
        self._trip(self._delivery(3), operator=self.other_driver)
        self.authenticate("drv_driver", "drv_driver")

        trips = self._rpc("/stock_fleet_trace/driver/trips")

        self.assertEqual(
            trips,
            [
                {
                    "id": mine.id,
                    "name": mine.name,
                    "vehicle": self.vehicle.display_name,
                    "state": "planned",
                    "stop_count": 1,
                }
            ],
        )

    def test_a_chain_sent_over_http_is_applied(self):
        delivered = self._delivery(5)
        absent = self._delivery(2)
        trip = self._trip(delivered | absent)
        trip.action_depart()
        self.authenticate("drv_driver", "drv_driver")
        package = self._rpc(f"/stock_fleet_trace/trip/{trip.id}/package")
        self.assertEqual(package["chain_head"], "")
        self.assertIn(self.absent.id, [r["id"] for r in package["unbatch_reasons"]])
        Event = self.env["stock.trip.offline.event"]
        events = [
            {
                "event_type": "deliver",
                "picking_id": delivered.id,
                "payload": {
                    "receiver_name": "José Muñoz",
                    "signature": TEST_PNG_B64,
                },
            },
            {
                "event_type": "not_delivered",
                "picking_id": absent.id,
                "payload": {"reason_id": self.absent.id, "note": "Portón cerrado"},
            },
            {
                "event_type": "incident",
                "picking_id": False,
                "payload": {
                    "incident": {"incident_type": "spill", "description": "Bulto roto"}
                },
            },
        ]
        chain_hash = package["chain_head"]
        for event in events:
            event.update(
                client_uuid=str(uuid4()),
                captured_at="2026-09-29T09:30:00-06:00",
                latitude=20.6597,
                longitude=-103.3496,
                device_uuid="phone-1",
                prev_hash=chain_hash,
            )
            event["event_hash"] = chain_hash = Event._trip_hash_event(event)

        result = self._rpc(
            f"/stock_fleet_trace/trip/{trip.id}/events",
            events=events,
            head=chain_hash,
        )

        self.assertEqual(
            result,
            {e["client_uuid"]: {"state": "applied", "error": False} for e in events},
        )
        self.assertEqual(delivered.state, "done")
        self.assertEqual(delivered.trip_receiver_name, "José Muñoz")
        self.assertEqual(str(delivered.date_done), "2026-09-29 15:30:00")
        self.assertFalse(absent.batch_id)
        self.assertEqual(trip.trip_incident_ids.incident_type, "spill")
        self.assertFalse(trip.trip_offline_chain_broken)
        self.assertEqual(trip.trip_offline_phone_head, chain_hash)
        package = self._rpc(f"/stock_fleet_trace/trip/{trip.id}/package")
        self.assertEqual(package["chain_head"], chain_hash)

    def test_the_driver_works_two_stops_from_the_screen(self):
        delivered = self._delivery(5)
        absent = self._delivery(2)
        trip = self._trip(delivered | absent)
        trip.action_depart()
        stops = trip.with_user(self.driver_user)._trip_offline_package()["stops"]
        self.assertEqual(len(stops), 2, stops)
        code = """
            (async () => {
                const wait = async (check) => {
                    const start = Date.now();
                    while (!check()) {
                        if (Date.now() - start > 20000) {
                            throw new Error("timeout: " + document.body.innerText);
                        }
                        await new Promise((resolve) => setTimeout(resolve, 100));
                    }
                };
                const openStop = async (name) => {
                    [...document.querySelectorAll(".sft-stop")]
                        .find((stop) => stop.textContent.includes(name))
                        .click();
                    await wait(() => document.querySelector(".sft-actions"));
                };
                await openStop("DELIVERED_NAME");
                const input = document.getElementById("sft-scan");
                input.value = "NOT-ON-BOARD";
                input.form.requestSubmit();
                await wait(() => document.querySelector(".sft-message-warn"));
                document.querySelector(".sft-actions .sft-btn-success").click();
                await wait(() => document.querySelector(".sft-form"));
                document.querySelector(".sft-form input").value = "José Muñoz";
                document.querySelector(".sft-form").requestSubmit();
                await wait(() => document.querySelector(".sft-history li"));
                document.querySelector(".sft-back").click();
                await wait(() => document.querySelectorAll(".sft-stop").length === 2);
                await openStop("ABSENT_NAME");
                document.querySelector(".sft-actions .sft-btn-danger").click();
                await wait(() => document.querySelector(".sft-form select"));
                const reason = document.querySelector(".sft-form select");
                reason.value = reason.options[1].value;
                document.querySelector(".sft-form").requestSubmit();
                // Not delivered, the stop leaves the trip on the server; the
                // phone still shows it with its result.
                await wait(() => {
                    const item = document.querySelector(".sft-history li");
                    return (
                        item &&
                        item.textContent.includes("Not delivered") &&
                        item.textContent.includes("Applied")
                    );
                });
                // Every trip of the driver is on the phone, not only the one opened.
                const packages = () =>
                    new Promise((resolve, reject) => {
                        const request = indexedDB.open("stock_fleet_trace_driver");
                        request.onerror = () => reject(request.error);
                        request.onsuccess = () => {
                            const all = request.result
                                .transaction("packages")
                                .objectStore("packages")
                                .getAll();
                            all.onsuccess = () => resolve(all.result);
                        };
                    });
                const start = Date.now();
                while (!(await packages()).some((p) => p.trip.name === "OTHER_TRIP")) {
                    if (Date.now() - start > 20000) {
                        throw new Error("the other trip was not downloaded");
                    }
                    await new Promise((resolve) => setTimeout(resolve, 200));
                }
                console.log("test successful");
            })().catch((error) => console.error(error.message));
        """
        other = self._trip(self._delivery(1))
        code = (
            code.replace("DELIVERED_NAME", delivered.name)
            .replace("ABSENT_NAME", absent.name)
            .replace("OTHER_TRIP", other.name)
        )
        self.browser_js(
            f"/stock_fleet_trace/driver?trip={trip.id}",
            code,
            ready="!!document.querySelector('.sft-stop')",
            login="drv_driver",
            timeout=120,
        )

        self.assertEqual(delivered.state, "done")
        self.assertEqual(delivered.trip_receiver_name, "José Muñoz")
        self.assertFalse(absent.batch_id)
        events = trip.trip_offline_event_ids.sorted("id")
        self.assertEqual(events.mapped("state"), ["applied", "applied"])
        self.assertEqual(events[1].prev_hash, events[0].event_hash)
        self.assertFalse(trip.trip_offline_chain_broken)
        self.assertTrue(all(events.mapped("device_uuid")))

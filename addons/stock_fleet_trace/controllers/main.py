import hashlib
import json

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request
from odoo.tools import file_open

DRIVER_PAGE = "/stock_fleet_trace/driver"
DRIVER_STATIC = "stock_fleet_trace/static/driver"
DRIVER_SHELL_FILES = ("app.js", "canonical.js", "db.js", "driver.css", "sw.js")


def _driver_terms(env):
    _ = env._
    return {
        "title": _("Driver Screen"),
        "loading": _("Loading…"),
        "my_trips": _("My trips"),
        "log_out": _("Log out"),
        "log_out_offline": _("Log out (needs internet)"),
        "log_out_pending": _(
            "This phone still has %(count)s events to send. They stay saved on "
            "this phone and go out the next time you sign in with this user. "
            "Log out anyway?"
        ),
        "refresh": _("Refresh"),
        "no_trips": _("You have no trips to work."),
        "no_trips_offline": _(
            "No connection: only the trips already downloaded are shown."
        ),
        "downloaded": _("Downloaded"),
        "stop_count": _("%(count)s stops"),
        "downloading": _("Downloading the trip…"),
        "download_failed": _(
            "The trip could not be downloaded. Connect and try again."
        ),
        "package_downloaded": _("Trip downloaded: %(time)s"),
        "trip_planned": _("Planned: wait for the warehouse to load it"),
        "trip_loaded": _("Loaded"),
        "trip_in_transit": _("In transit"),
        "trip_closed": _("Closed"),
        "trip_returned": _("Returned"),
        "trip_cancelled": _("Cancelled"),
        "back": _("Back"),
        "stops": _("Stops"),
        "no_stops": _("This trip has no stops."),
        "status_todo": _("To deliver"),
        "status_left": _("Left the trip"),
        "status_done": _("Delivered"),
        "status_cancel": _("Cancelled"),
        "status_deliver": _("Delivered"),
        "status_partial": _("Partial"),
        "status_not_delivered": _("Not delivered"),
        "status_incident": _("Incident"),
        "status_scan": _("Lot checked"),
        "state_pending": _("Pending"),
        "state_applied": _("Applied"),
        "state_review": _("To review"),
        "state_dismissed": _("Dismissed"),
        "not_sent": _("Not sent"),
        "to_review": _("To review"),
        "stop_closed": _("Stop recorded: %(status)s."),
        "history": _("Recorded on this phone"),
        "open_map": _("Map"),
        "product": _("Product"),
        "lot": _("Lot"),
        "quantity": _("Quantity"),
        "checked": _("Checked"),
        "no_lines": _("No goods on board for this stop."),
        "scan_placeholder": _("Scan or type a delivery slip or lot"),
        "check": _("Check"),
        "camera": _("Camera"),
        "camera_unsupported": _(
            "This phone cannot read codes with the camera: use the scanner or "
            "type the code."
        ),
        "camera_unavailable": _(
            "The camera could not be opened. Allow it for this page or type the code."
        ),
        "scan_stop": _("Stop %(stop)s: %(customer)s"),
        "scan_stop_full": _(
            "Stop %(stop)s: %(customer)s. %(units)s units registered; scan a lot "
            "only to check it."
        ),
        "scan_trip_sheet": _("That is the sheet of BATCH %(trip)s."),
        "scan_unknown": _(
            "Code %(code)s is not a delivery slip nor a lot on board of BATCH %(trip)s."
        ),
        "scan_lot_goes_to": _("Lot %(lot)s goes to: %(stops)s"),
        "scan_lot_ok": _(
            "Lot %(lot)s is correct: %(product)s (%(scanned)s of %(board)s)"
        ),
        "scan_lot_other_stop": _(
            "STOP: lot %(lot)s is not for %(stop)s, it goes to %(stops)s. Do not "
            "hand it over."
        ),
        "scan_lot_not_on_board": _(
            "STOP: lot %(lot)s is not on board for %(stop)s. Check the product "
            "before handing it over."
        ),
        "action_deliver": _("Delivered"),
        "action_partial": _("Partial"),
        "action_not_delivered": _("Not delivered"),
        "action_incident": _("Incident"),
        "receiver_name": _("Received by"),
        "signature": _("Signature"),
        "clear": _("Clear"),
        "partial_note": _("What did the customer take?"),
        "note_required": _("Write what the customer took."),
        "reason": _("Reason"),
        "choose_reason": _("Choose the reason"),
        "reason_required": _("Choose the reason it was not delivered."),
        "note": _("Note"),
        "incident_type": _("Type"),
        "choose_incident_type": _("Choose the type"),
        "description": _("Description"),
        "incident_required": _("Choose the type and describe the incident."),
        "cancel": _("Cancel"),
        "save": _("Save"),
        "saving": _("Saving…"),
        "saved": _("Saved on the phone. It is sent as soon as there is signal."),
        "online": _("Online"),
        "offline": _("No signal"),
        "pending_count": _("Pending: %(count)s"),
        "last_sync": _("Last sync: %(time)s"),
        "never": _("never"),
        "syncing": _("Syncing…"),
        "sync_now": _("Sync"),
        "sync_error": _("Could not sync: %(error)s"),
        "other_user_pending": _("%(count)s of another driver"),
        "deliver_scans_incomplete": _(
            "Lots were scanned here but not all the goods: scan everything or use "
            "Partial."
        ),
        "session_expired": _(
            "Your session expired: log in. What you captured stays on the phone."
        ),
    }


def _driver_version():
    digest = hashlib.sha256()
    for name in DRIVER_SHELL_FILES:
        with file_open(f"{DRIVER_STATIC}/{name}", "rb") as file:
            digest.update(file.read())
    return digest.hexdigest()[:16]


class StockFleetTraceOffline(http.Controller):
    def _trip(self, batch_id):
        batch = request.env["stock.picking.batch"].browse(batch_id).exists()
        if not batch:
            raise NotFound
        return batch

    @http.route(
        "/stock_fleet_trace/trip/<int:batch_id>/package",
        methods=["POST"],
        type="jsonrpc",
        auth="user",
    )
    def trip_package(self, batch_id, head=None):
        batch = self._trip(batch_id)
        package = batch._trip_offline_package(head=head)
        package["chain_head"] = batch._trip_last_event_hash()
        return package

    @http.route(
        "/stock_fleet_trace/trip/<int:batch_id>/events",
        methods=["POST"],
        type="jsonrpc",
        auth="user",
    )
    def trip_events(self, batch_id, events, head=None):
        return self._trip(batch_id)._trip_receive_offline_events(events, head=head)

    @http.route(DRIVER_PAGE, methods=["GET"], type="http", auth="user", readonly=True)
    def driver_screen(self, **kwargs):
        env = request.env
        terms = self._get_driver_terms(env)
        boot = {
            "terms": terms,
            "user_name": env.user.name,
            "user_id": env.user.id,
            "service_worker": f"{DRIVER_PAGE}/sw.js",
            "scope": DRIVER_PAGE,
        }
        return request.render(
            "stock_fleet_trace.driver_screen_page",
            {
                "boot": json.dumps(boot, ensure_ascii=False),
                "terms": terms,
                "plugins": self._get_driver_plugins(),
                "lang": (env.lang or "en_US").replace("_", "-"),
            },
        )

    def _get_driver_terms(self, env):
        return _driver_terms(env)

    def _get_driver_plugins(self):
        return []

    @http.route(
        f"{DRIVER_PAGE}/manifest.webmanifest",
        methods=["GET"],
        type="http",
        auth="user",
        readonly=True,
    )
    def driver_manifest(self):
        title = request.env._("Driver Screen")
        manifest = {
            "id": DRIVER_PAGE,
            "name": title,
            "short_name": request.env._("Deliveries"),
            "start_url": DRIVER_PAGE,
            "scope": DRIVER_PAGE,
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#f3f4f2",
            "theme_color": "#1f6f43",
            "icons": [
                {
                    "src": f"/web/static/img/odoo-icon-{size}x{size}.png",
                    "sizes": f"{size}x{size}",
                    "type": "image/png",
                }
                for size in (192, 512)
            ],
        }
        return request.prepare_json_response(
            manifest, [("Content-Type", "application/manifest+json")]
        )

    @http.route(
        f"{DRIVER_PAGE}/sw.js",
        methods=["GET"],
        type="http",
        auth="public",
        readonly=True,
    )
    def driver_service_worker(self):
        with file_open(f"{DRIVER_STATIC}/sw.js") as file:
            content = file.read().replace("__SFT_DRIVER_VERSION__", _driver_version())
        return request.prepare_response(
            content,
            headers=[
                ("Content-Type", "text/javascript"),
                ("Service-Worker-Allowed", DRIVER_PAGE),
                ("Cache-Control", "no-cache"),
            ],
        )

    @http.route(
        f"{DRIVER_PAGE}/trips",
        methods=["POST"],
        type="jsonrpc",
        auth="user",
        readonly=True,
    )
    def driver_trips(self):
        return request.env["stock.picking.batch"]._trip_driver_trips()

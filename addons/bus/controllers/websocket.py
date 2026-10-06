from urllib.parse import urlsplit

from odoo.http import (
    Controller,
    SessionExpiredException,
    request,
    resolve_cors_same_host,
    route,
)
from odoo.libs.json import dumps as json_dumps
from odoo.tools import config

from ..models.bus import channel_with_db, dispatch
from ..websocket import WebsocketConnectionHandler


def _origin_port_parts(url: str) -> tuple[str, str, int | None] | None:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    return (parts.scheme, parts.hostname, port) if parts.hostname else None


def resolve_cors_worker_bundle(request) -> str | None:
    # Prefork without a reverse proxy serves pages on the HTTP port and the bus
    # on the evented one: a page of this server's own HTTP port fetches the
    # worker bundle from the evented port, which is another origin
    if allowed := resolve_cors_same_host(request):
        return allowed
    origin = request.httprequest.headers.get("Origin")
    theirs = origin and _origin_port_parts(origin)
    ours = _origin_port_parts(request.httprequest.host_url)
    if not theirs or not ours:
        return None
    if (
        theirs[:2] == ours[:2]
        and theirs[2] == config["http_port"]
        and ours[2] == config["gevent_port"]
    ):
        return origin
    return None


class WebsocketController(Controller):
    @route("/websocket", type="http", auth="public", cors="*", websocket=True)
    def websocket(self, version=None):
        return WebsocketConnectionHandler.open_connection(request, version)

    @route("/websocket/health", type="http", auth="none", save_session=False)
    def health(self):
        healthy = dispatch.is_healthy
        data = json_dumps({"status": "pass" if healthy else "fail"})
        headers = [("Content-Type", "application/json"), ("Cache-Control", "no-store")]
        return request.prepare_response(data, headers, status=200 if healthy else 503)

    @route("/websocket/peek_notifications", type="jsonrpc", auth="public", cors="*")
    def peek_notifications(self, channels, last, is_first_poll=False):
        if is_first_poll:
            request.session["is_websocket_session"] = True
        elif "is_websocket_session" not in request.session:
            raise SessionExpiredException
        subscribe_data = request.env["ir.websocket"]._prepare_subscribe_data(
            channels, last
        )
        request.env["ir.websocket"]._after_subscribe_data(subscribe_data)
        channels_with_db = [
            channel_with_db(request.db, c) for c in subscribe_data["channels"]
        ]
        notifications = request.env["bus.bus"]._poll(
            channels_with_db, subscribe_data["last"]
        )
        return {"channels": channels_with_db, "notifications": notifications}

    @route("/websocket/on_closed", type="jsonrpc", auth="public", cors="*")
    def on_websocket_closed(self):
        request.env["ir.websocket"]._on_websocket_closed(request.cookies)

    @route(
        "/bus/websocket_worker_bundle",
        type="http",
        auth="public",
        cors=resolve_cors_worker_bundle,
        cors_credentials=True,
    )
    def get_websocket_worker_bundle(self, v=None):  # pylint: disable=unused-argument
        bundle = request.env["ir.qweb"]._get_websocket_worker_bundle()
        if bundle:
            url, code = bundle
            response = request.prepare_response(
                code,
                [
                    ("Content-Type", "text/javascript; charset=utf-8"),
                    ("Cache-Control", "no-cache"),
                ],
            )
            response.set_etag(url.rsplit("/", 2)[-2])
            response.make_conditional(request.httprequest)
        else:
            response = request.redirect("/bus/static/src/workers/bus_worker_script.js")
        return response

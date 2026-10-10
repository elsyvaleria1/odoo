from odoo.http import Controller, request, route
from odoo.libs.json import dumps as json_dumps

from ..models.bus import dispatch
from ..websocket import WebsocketConnectionHandler


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

    @route("/bus/websocket_worker_bundle", type="http", auth="public")
    def get_websocket_worker_bundle(self, v=None):  # pylint: disable=unused-argument
        return self._websocket_worker_bundle_response()

    # A page of another site -- a live chat embedded there -- cannot start a
    # worker from this server's origin: it reads the same public code here,
    # without credentials, and starts it from a blob.
    @route(
        "/bus/websocket_worker_bundle/anonymous",
        type="http",
        auth="public",
        cors="*",
        save_session=False,
    )
    def get_anonymous_websocket_worker_bundle(self, v=None):  # pylint: disable=unused-argument
        return self._websocket_worker_bundle_response()

    def _websocket_worker_bundle_response(self):
        bundle = request.env["ir.qweb"]._get_websocket_worker_bundle()
        if not bundle:
            return request.redirect("/bus/static/src/workers/bus_worker_script.js")
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
        return response

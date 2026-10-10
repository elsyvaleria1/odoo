import hashlib
import re

from werkzeug.exceptions import NotFound

from odoo.http import Controller, request, route
from odoo.libs.json import dumps as json_dumps
from odoo.tools import file_open

from ..models.bus import dispatch
from ..websocket import WebsocketConnectionHandler

WORKER_SOURCE_ROUTE = "/bus/websocket_worker_source/"
_WORKER_IMPORT = re.compile(
    r"""(\b(?:from|import)\s*)(["'])(?:\./|@bus/workers/)(\w+)(?:\.js)?\2"""
)


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
            return request.redirect(f"{WORKER_SOURCE_ROUTE}bus_worker_script.js")
        url, code = bundle
        return self._javascript_response(code, url.rsplit("/", 2)[-2])

    def _javascript_response(self, code, etag):
        response = request.prepare_response(
            code,
            [
                ("Content-Type", "text/javascript; charset=utf-8"),
                ("Cache-Control", "no-cache"),
            ],
        )
        response.set_etag(etag)
        response.make_conditional(request.httprequest)
        return response

    # Without a standalone build the worker runs its source files, where no
    # import map resolves @bus/workers/...; nor does a blob, which is how
    # another site starts it. Every import names this route, absolute.
    @route(
        f"{WORKER_SOURCE_ROUTE}<string:name>.js",
        type="http",
        auth="public",
        cors="*",
        save_session=False,
    )
    def get_websocket_worker_source(self, name):
        if not re.fullmatch(r"\w+", name):
            raise NotFound
        try:
            with file_open(f"bus/static/src/workers/{name}.js", "rb") as source:
                code = source.read().decode()
        except FileNotFoundError:
            raise NotFound from None
        base = request.httprequest.host_url.rstrip("/") + WORKER_SOURCE_ROUTE
        code = _WORKER_IMPORT.sub(
            lambda match: f"{match[1]}{match[2]}{base}{match[3]}.js{match[2]}", code
        )
        return self._javascript_response(
            code, hashlib.sha256(code.encode()).hexdigest()[:32]
        )

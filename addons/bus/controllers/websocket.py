import hashlib
import posixpath
import re

from werkzeug.exceptions import NotFound

from odoo.http import Controller, request, route
from odoo.libs.json import dumps as json_dumps
from odoo.tools import file_open
from odoo.tools.assets.esm_graph import url_to_module_path

from ..models.bus import dispatch
from ..websocket import WebsocketConnectionHandler

WORKER_SOURCE_ROUTE = "/bus/websocket_worker_source"
_IMPORT = re.compile(r"""(\b(?:from|import)\s*)(["'])([^"'\n]+)\2""")


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
            return request.redirect(WORKER_SOURCE_ROUTE)
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

    # Without a standalone build the worker runs the bundle's source files,
    # all of them in bundle order as the build would. No import map resolves
    # a specifier in a worker, nor a relative path in one started from a blob,
    # which is how another site starts it: every import names this route,
    # absolute.
    @route(
        WORKER_SOURCE_ROUTE,
        type="http",
        auth="public",
        cors="*",
        save_session=False,
    )
    def get_websocket_worker_entry(self):
        base = self._worker_source_base()
        code = "".join(
            f'import "{base}/{path}";\n'
            for path in request.env["ir.qweb"]._get_websocket_worker_sources()
        )
        return self._javascript_response(code, _digest(code))

    @route(
        f"{WORKER_SOURCE_ROUTE}/<path:path>",
        type="http",
        auth="public",
        cors="*",
        save_session=False,
    )
    def get_websocket_worker_source(self, path):
        sources = request.env["ir.qweb"]._get_websocket_worker_sources()
        if path not in sources:
            raise NotFound
        with file_open(sources[path], "rb") as source:
            code = source.read().decode()
        specifiers = {url_to_module_path(f"/{known}"): known for known in sources}
        base = self._worker_source_base()

        def rewrite(match):
            imported = match[3]
            if imported.startswith("."):
                imported = posixpath.normpath(
                    posixpath.join(posixpath.dirname(path), imported)
                )
                if not imported.endswith(".js"):
                    imported += ".js"
            else:
                imported = specifiers.get(imported)
            if imported not in sources:
                return match[0]
            return f"{match[1]}{match[2]}{base}/{imported}{match[2]}"

        code = _IMPORT.sub(rewrite, code)
        return self._javascript_response(code, _digest(code))

    def _worker_source_base(self):
        return request.httprequest.host_url.rstrip("/") + WORKER_SOURCE_ROUTE


def _digest(code):
    return hashlib.sha256(code.encode()).hexdigest()[:32]

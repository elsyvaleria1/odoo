import logging
import os
from typing import Any

import psycopg

import odoo.db
from odoo import http
from odoo.http import Response, request
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.service import server as service_server
from odoo.service.metrics import CONTENT_TYPE as METRICS_CONTENT_TYPE
from odoo.service.metrics import get_metrics_token, render_prometheus_exposition
from odoo.tools import config, str2bool
from odoo.tools.misc import consteq

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


def _is_db_server_reachable(probe: str) -> bool:
    try:
        with (
            _debug.perf("postgres_probe", probe=probe),
            odoo.db.db_connect("postgres").cursor(),
        ):
            return True
    except psycopg.Error as exc:
        _debug.logic("postgres_probe_failed", probe=probe, error=type(exc).__name__)
        return False


class Health(http.Controller):
    @http.route(
        "/web/health", type="http", auth="none", save_session=False, database=False
    )
    def health(self, db_server_status: bool | str = False) -> Response:
        health_info: dict[str, Any] = {"status": "pass"}
        status = 200
        if str2bool(db_server_status, False):
            reachable = _is_db_server_reachable("health")
            health_info["db_server_status"] = reachable
            if not reachable:
                health_info["status"] = "fail"
                status = 500
        _debug.lifecycle("health", status=status, info=health_info)
        return self._get_health_response(health_info, status)

    @http.route(
        "/web/healthz", type="http", auth="none", save_session=False, database=False
    )
    def healthz(self) -> Response:
        _debug.lifecycle("healthz")
        return self._get_health_response({"status": "pass"}, 200)

    @http.route(
        "/web/readyz", type="http", auth="none", save_session=False, database=False
    )
    def readyz(self) -> Response:
        checks: dict[str, str] = {}
        status = 200
        if _is_db_server_reachable("readyz"):
            checks["db"] = "pass"
        else:
            checks["db"] = "fail"
            status = 503
        if os.access(config["data_dir"], os.W_OK):
            checks["data_dir"] = "pass"
        else:
            _debug.logic("readyz_data_dir_not_writable", data_dir=config["data_dir"])
            checks["data_dir"] = "fail"
            status = 503
        if service_server.is_ready():
            checks["registries"] = "pass"
        else:
            _debug.logic("readyz_registry_preload_in_progress")
            checks["registries"] = "loading"
            status = 503
        _debug.lifecycle("readyz", status=status, checks=checks)
        return self._get_health_response(
            {"status": "pass" if status == 200 else "fail", "checks": checks},
            status,
        )

    @http.route(
        "/web/metrics", type="http", auth="none", save_session=False, database=False
    )
    def metrics(self) -> Response:
        token = get_metrics_token()
        _debug.lifecycle("metrics", token_configured=bool(token))
        if not token:
            raise request.prepare_not_found_error()
        presented = request.httprequest.headers.get("Authorization", "")
        scheme, _, offered = presented.partition(" ")
        if scheme.lower() != "bearer" or not consteq(offered.strip(), token):  # noqa: E8537 -- device: a device's or a service's credential, presented by a program
            _debug.logic(
                "metrics_rejected", scheme=scheme, token_presented=bool(offered)
            )
            _logger.warning(
                "Rejected /web/metrics scrape from %s: bad or missing bearer token",
                request.httprequest.remote_addr,
            )
            return request.prepare_response(
                "", [("Cache-Control", "no-store")], status=401
            )
        with _debug.perf("metrics_render_exposition"):
            exposition = render_prometheus_exposition()
        _debug.perf.count("metrics_exposition_size", size=len(exposition))
        return request.prepare_response(
            exposition,
            [("Content-Type", METRICS_CONTENT_TYPE), ("Cache-Control", "no-store")],
            status=200,
        )

    def _get_health_response(self, payload: dict[str, Any], status: int) -> Response:
        return request.prepare_response(
            json_dumps(payload),
            [
                ("Content-Type", "application/json"),
                ("Cache-Control", "no-store"),
            ],
            status=status,
        )

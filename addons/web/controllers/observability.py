import logging
import math

from odoo import modules
from odoo.http import Controller, Response, request, route
from odoo.libs.debug_log import DebugLog
from odoo.libs.fixed_window import FixedWindowLimiter
from odoo.libs.json import loads as json_loads
from odoo.libs.sql import INT4_MAX
from odoo.tools import config

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_limiter = FixedWindowLimiter(window=60, limit=120)


def _get_client_rate_key(prefix: str) -> str:
    uid = request.session.uid
    ident = f"uid:{uid}" if uid else f"ip:{request.httprequest.remote_addr or 'anon'}"
    return f"{prefix}:{ident}"


_MAX_LATENCY_MS = 60_000
_MAX_CLS = 5.0
_MAX_URL_LEN = 500
_MAX_UA_LEN = 500
_MAX_ERROR_MSG_LEN = 4_096
_MAX_ERROR_STACK_LEN = 4_096
_MAX_ERROR_CAUSE_LEN = 4_096
_MAX_ERROR_FILENAME_LEN = 500

_JS_ERROR_KINDS = frozenset(
    {
        "error",
        "unhandledrejection",
        "module_rebind",
        "service_start",
        "asset_load_error",
    }
)
_JS_ERROR_PHASES = frozenset({"pre_boot", "post_boot", "boot_mount_failed"})


def _get_clamped_metric(value, maximum: float) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if not math.isfinite(value) or value < 0 or value > maximum:
        return None
    return float(value)


def _get_capped_str(raw, cap: int) -> str:
    return raw[:cap] if isinstance(raw, str) else ""


def _get_positive_int(raw) -> int:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return 0
    if not 0 <= raw <= INT4_MAX:
        return 0
    return int(raw)


def _read_beacon_payload(prefix: str) -> dict | Response:
    _debug.lifecycle(
        "beacon_received", prefix=prefix, bytes=len(request.httprequest.data or b"")
    )
    if _limiter.is_limited(_get_client_rate_key(prefix)):
        _debug.logic(
            "beacon_rejected", prefix=prefix, reason="rate_limited", status=429
        )
        return Response("", status=429, mimetype="text/plain")
    try:
        payload = json_loads(request.httprequest.data or b"{}")
    except ValueError, TypeError:
        _debug.logic(
            "beacon_rejected", prefix=prefix, reason="invalid_json", status=400
        )
        return Response("invalid json", status=400, mimetype="text/plain")
    if not isinstance(payload, dict):
        _debug.logic(
            "beacon_rejected",
            prefix=prefix,
            reason="not_a_dict",
            payload_type=type(payload).__name__,
            status=400,
        )
        return Response("invalid payload", status=400, mimetype="text/plain")
    return payload


def _prepare_js_error_values(payload: dict) -> dict | None:
    message = _get_capped_str(payload.get("message"), _MAX_ERROR_MSG_LEN)
    if not message:
        return None

    kind = payload.get("kind") if payload.get("kind") in _JS_ERROR_KINDS else "error"

    return {
        "message": message,
        "kind": kind,
        "phase": (
            payload.get("phase")
            if payload.get("phase") in _JS_ERROR_PHASES
            else "unknown"
        ),
        "filename": _get_capped_str(payload.get("filename"), _MAX_ERROR_FILENAME_LEN),
        "url": _get_capped_str(payload.get("url"), _MAX_URL_LEN),
        "user_agent": _get_capped_str(payload.get("user_agent"), _MAX_UA_LEN),
        "stack": _get_capped_str(payload.get("stack"), _MAX_ERROR_STACK_LEN),
        "cause": _get_capped_str(payload.get("cause"), _MAX_ERROR_CAUSE_LEN),
        "line": _get_positive_int(payload.get("line")),
        "col": _get_positive_int(payload.get("col")),
        "reloaded": (
            bool(payload.get("reloaded"))
            if kind == "asset_load_error" and "reloaded" in payload
            else None
        ),
    }


class Observability(Controller):
    @route(
        "/web/observability/cwv",
        type="http",
        auth="public",
        sitemap=False,
        methods=["POST"],
        csrf=False,
    )
    def cwv(self) -> Response:  # noqa: E8528 - a sendBeacon telemetry post, which cannot carry a CSRF token
        payload = _read_beacon_payload("cwv")
        if isinstance(payload, Response):
            return payload

        lcp = _get_clamped_metric(payload.get("lcp"), _MAX_LATENCY_MS)
        fcp = _get_clamped_metric(payload.get("fcp"), _MAX_LATENCY_MS)
        ttfb = _get_clamped_metric(payload.get("ttfb"), _MAX_LATENCY_MS)
        inp = _get_clamped_metric(payload.get("inp"), _MAX_LATENCY_MS)
        cls = _get_clamped_metric(payload.get("cls"), _MAX_CLS)
        url = _get_capped_str(payload.get("url"), _MAX_URL_LEN).split("?", 1)[0]
        user_agent = _get_capped_str(payload.get("user_agent"), _MAX_UA_LEN)
        pageview_id = _get_capped_str(payload.get("pageview_id"), 64)

        if lcp is None and fcp is None and ttfb is None and cls is None and inp is None:
            _debug.logic("cwv_beacon_dropped", reason="no_metric", status=204)
            return Response("", status=204)

        if not url:
            _debug.logic("cwv_beacon_dropped", reason="no_url", status=204)
            return Response("", status=204)

        uid = request.session.uid or False
        _logger.info(
            "[cwv] uid=%s url=%r lcp=%s fcp=%s cls=%s ttfb=%s inp=%s ua=%r",
            uid or "anon",
            url,
            lcp,
            fcp,
            cls,
            ttfb,
            inp,
            user_agent,
        )
        Metric = request.env["web.cwv.metric"].sudo()
        values = {
            "url": url,
            "user_id": uid,
            "lcp": lcp,
            "fcp": fcp,
            "cls": cls,
            "ttfb": ttfb,
            "inp": inp,
            "user_agent": user_agent or False,
            "pageview_id": pageview_id or False,
        }
        with _debug.perf("cwv_beacon_record", cr=request.env.cr, pageview=pageview_id):
            Metric._record_beacon(values)
        return Response("", status=204)

    @route(
        "/web/observability/js_error",
        type="http",
        auth="public",
        sitemap=False,
        methods=["POST"],
        csrf=False,
    )
    def js_error(self) -> Response:  # noqa: E8528 - a sendBeacon telemetry post, which cannot carry a CSRF token
        payload = _read_beacon_payload("js_error")
        if isinstance(payload, Response):
            return payload

        beacon = _prepare_js_error_values(payload)
        if beacon is None:
            _debug.logic("js_error_beacon_dropped", reason="no_message", status=204)
            return Response("", status=204)

        uid = request.session.uid or False
        in_test = bool(modules.module.current_test) or config["test_enable"]
        level = (
            logging.DEBUG
            if beacon["kind"] == "module_rebind" and in_test
            else logging.WARNING
        )
        _debug.logic(
            "js_error_beacon_level",
            kind=beacon["kind"],
            phase=beacon["phase"],
            in_test=in_test,
            level=logging.getLevelName(level),
        )
        _logger.log(
            level,
            "[js_error] uid=%s phase=%s kind=%s reloaded=%s msg=%r cause=%r"
            " at %r:%d:%d url=%r ua=%r stack=%r",
            uid or "anon",
            beacon["phase"],
            beacon["kind"],
            beacon["reloaded"],
            beacon["message"],
            beacon["cause"],
            beacon["filename"],
            beacon["line"],
            beacon["col"],
            beacon["url"],
            beacon["user_agent"],
            beacon["stack"],
        )
        reloaded = beacon["reloaded"]
        with _debug.perf(
            "js_error_beacon_record", cr=request.env.cr, kind=beacon["kind"]
        ):
            request.env["web.js.error"].sudo()._record_beacon(
                {
                    "user_id": uid,
                    **beacon,
                    "reloaded": (
                        None
                        if reloaded is None
                        else ("reloaded" if reloaded else "suppressed")
                    ),
                }
            )
        return Response("", status=204)

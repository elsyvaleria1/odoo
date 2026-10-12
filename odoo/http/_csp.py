from __future__ import annotations

import functools
import re
import secrets
from typing import Any

from markupsafe import Markup

from odoo.libs.debug_log import DebugLog

from ._protocols import RequestState

_debug = DebugLog(__name__)

CSP_MODE_PARAMETER = "http.csp_mode"
CSP_ENFORCE = "enforce"
CSP_REPORT_ONLY = "report-only"
CSP_OFF = "off"
CSP_MODES = frozenset({CSP_ENFORCE, CSP_REPORT_ONLY, CSP_OFF})

_SCRIPT_OPEN_RE = re.compile(r"<script(?=[\s/>])", re.IGNORECASE)
_NONCE_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")


def get_script_policy(nonce: str, *, unsafe_eval: bool) -> str:
    sources = [f"'nonce-{nonce}'", "'strict-dynamic'"]
    if unsafe_eval:
        sources.append("'unsafe-eval'")
    sources += ["'unsafe-inline'", "https:"]
    return f"script-src {' '.join(sources)}; object-src 'none'; base-uri 'self'"


def _declares_script_sources(policy: str) -> bool:
    for directive in policy.split(";"):
        name = directive.strip().partition(" ")[0].lower()
        if name in ("script-src", "default-src"):
            return True
    return False


def apply_script_policy(response: Any, request: RequestState) -> None:
    headers = response.headers
    if not headers.get("Content-Type", "").lower().startswith("text/html"):
        return
    mode = request.csp_mode
    if mode == CSP_OFF:
        _debug.logic("http.csp.skipped", reason="off")
        return
    existing = headers.get("Content-Security-Policy", "")
    if _declares_script_sources(existing):
        _debug.logic("http.csp.skipped", reason="response_policy")
        return
    policy = get_script_policy(request.csp_nonce, unsafe_eval=request.csp_unsafe_eval)
    if mode == CSP_REPORT_ONLY:
        headers["Content-Security-Policy-Report-Only"] = policy
    elif existing:
        headers["Content-Security-Policy"] = f"{existing}; {policy}"
    else:
        headers["Content-Security-Policy"] = policy
    _debug.logic(
        "http.csp.applied",
        mode=mode,
        merged=bool(existing),
        unsafe_eval=request.csp_unsafe_eval,
    )


class _RequestCspMixin(RequestState):
    csp_unsafe_eval: bool = True
    csp_scripts_need_eval: bool = False

    def note_script_bundle(self, *, needs_eval: bool) -> None:
        if needs_eval:
            self.csp_scripts_need_eval = True
        self.csp_unsafe_eval = self.csp_scripts_need_eval
        _debug.logic(
            "http.csp.script_bundle",
            needs_eval=needs_eval,
            unsafe_eval=self.csp_unsafe_eval,
        )

    @functools.cached_property
    def csp_nonce(self) -> str:
        return secrets.token_urlsafe(18)

    @functools.cached_property
    def csp_mode(self) -> str:
        env = self.bound_env
        if env is None or env.cr.closed:
            return CSP_ENFORCE
        mode = (
            env["ir.config_parameter"].sudo().get_param(CSP_MODE_PARAMETER, CSP_ENFORCE)
        )
        if mode not in CSP_MODES:
            _debug.logic("http.csp.mode_unknown", value=mode)
            return CSP_ENFORCE
        return mode

    def adopt_csp_nonce(self, nonce: Any) -> bool:
        if self.dispatcher.routing_type == "http":
            msg = "an HTML response draws its own script nonce"
            raise RuntimeError(msg)
        if not isinstance(nonce, str) or not _NONCE_RE.fullmatch(nonce):
            _debug.logic("http.csp.nonce_refused", kind=type(nonce).__name__)
            return False
        self.__dict__["csp_nonce"] = nonce
        return True

    def nonce_scripts(self, html: str | None) -> Markup:
        if not html:
            return Markup("")
        return Markup(_SCRIPT_OPEN_RE.sub(f'<script nonce="{self.csp_nonce}"', html))

import contextlib
import logging
from typing import Any
from urllib.parse import urlsplit

import requests
from urllib3.util import parse_url

from odoo.libs.debug_log import DebugLog
from odoo.libs.guarded_http import RefusedDestination
from odoo.libs.netguard import DestinationRefused

__all__ = [
    "RESPONSE_MAX_BYTES",
    "deliver",
    "get_log_target",
    "get_refusal_explanation",
]

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

RESPONSE_MAX_BYTES = 1024 * 1024


def get_log_target(url: str) -> str:
    try:
        parts = parse_url(url)
    except ValueError:
        return "<malformed URL>"
    # urllib3 parses any text as a location: a "host" with whitespace in it
    # was never one
    if parts.host and any(char.isspace() for char in parts.host):
        return "<malformed URL>"
    host = parts.host if parts.scheme else None
    return (host or "").strip("[]") or "<unknown host>"


def get_refusal_explanation(refusal: DestinationRefused) -> str:
    if refusal.kind == "unresolvable":
        return (
            "The name resolved when the action ran and does not at delivery, "
            "so there was no address to send to."
        )
    if refusal.kind == "syntax":
        return (
            "The URL itself cannot be sent to as written, whatever its name "
            "resolves to: correct the action's URL."
        )
    return (
        "The destination passed the check when the action ran and is refused "
        "at delivery: its name now resolves elsewhere, or the delivery "
        "session's policy differs from the action's."
    )


def _spellings(url: str) -> set[str]:
    # an error names the URL as requests re-quoted it (%7C for |, o for %6F,
    # UTF-8 escapes for non-ASCII), not as the action spelled it
    forms = [url]
    with contextlib.suppress(requests.exceptions.RequestException, ValueError):
        forms.append(requests.Request("POST", url).prepare().url or "")
    needles = set()
    for form in forms:
        parsed = urlsplit(form)
        needles.add(form)
        if parsed.query:
            needles.add(f"{parsed.path}?{parsed.query}")
        if len(parsed.path) > 1:
            needles.add(parsed.path)
    needles.discard("")
    return needles


def _scrub_url(message: str, url: str, target: str) -> str:
    for needle in sorted(_spellings(url), key=len, reverse=True):
        message = message.replace(needle, f"<{target} webhook URL>")
    return message


def deliver(
    session: Any,
    url: str,
    timeout: float,
    action_label: str,
    target: str,
    json_values: bytes | str,
) -> None:
    _logger.debug("Webhook %s to %s - start", action_label, target)
    try:
        with _debug.perf("webhook_post", target=target, timeout=timeout):
            with session:
                response = session.post(
                    url,
                    data=json_values,
                    headers={"Content-Type": "application/json"},
                    timeout=timeout,
                    allow_redirects=False,
                )
        response.raise_for_status()
        _logger.info("Webhook %s to %s - succeeded", action_label, target)
        _debug.pipeline("webhook_delivered", target=target, status=response.status_code)
    except RefusedDestination as refusal:
        blocked = _scrub_url(str(refusal), url, target)
        _debug.logic("webhook_guard", phase="delivery", target=target, blocked=blocked)
        _logger.error(
            "Webhook %s to %s was NOT sent: %s. %s",
            action_label,
            target,
            blocked,
            get_refusal_explanation(refusal),
        )
    except requests.exceptions.ReadTimeout:
        _debug.logic("webhook_failed", target=target, reason="timeout")
        _logger.warning(
            "Webhook %s to %s timed out after %ss. The receiver may or "
            "may not have processed it. Raise 'Webhook Timeout (s)' on "
            "the action if the receiver is simply slow; if delivery has "
            "to be certain, this action cannot give you that.",
            action_label,
            target,
            timeout,
        )
    except requests.exceptions.RequestException as e:
        _debug.logic("webhook_failed", target=target, reason=type(e).__name__)
        _logger.error(
            "Webhook %s to %s failed and will NOT be retried: %s",
            action_label,
            target,
            _scrub_url(str(e), url, target),
        )

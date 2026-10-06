import logging
from collections.abc import Mapping
from typing import Any

from odoo import SUPERUSER_ID, api, models
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from ..tools.fingerprint import is_expected
from .error_incident import capture_payload

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

# The key under the JSON-RPC error's `data.context` that names the incident.
CONTEXT_KEY = "error_incident"


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _handle_error(cls, exception: Exception) -> Any:
        # Before `super()`: it serializes the error body, so the key must be on
        # the exception by then.
        cls._capture_request_error(exception)
        return super()._handle_error(exception)

    @classmethod
    def _capture_request_error(cls, exception: Exception) -> None:
        """Name the incident in the error the client receives; record it later.

        The request's cursor has been rolled back, may be read-only, and may
        already be closed: the occurrence is written once it is back in the
        pool, on a cursor of its own (`call_after_release`).
        """
        if is_expected(exception) or not request or not request.db:
            return
        try:
            httprequest = request.httprequest
            payload = capture_payload(
                exception,
                "request",
                user_id=request.env.uid if request.env else None,
                location=f"{httprequest.method} {httprequest.path}"[:500],
                request_ref=request.id,
            )
            context = getattr(exception, "context", None)
            exception.context = {
                **(context if isinstance(context, Mapping) else {}),
                CONTEXT_KEY: {
                    "fingerprint": payload["fingerprint"],
                    "occurrence": payload["occurrence_ref"],
                },
            }
        except Exception:
            _logger.exception("Could not take the occurrence of a request error")
            return
        registry = cls.pool

        def record() -> None:
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env["error.incident"]._capture_quietly(payload)

        request.call_after_release(record)
        _debug.logic(
            "incident.request_error",
            fingerprint=payload["fingerprint"],
            exception=payload["exception_type"],
        )

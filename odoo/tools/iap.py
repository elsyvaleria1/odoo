import logging
import uuid
from typing import TYPE_CHECKING, Any

import requests

from odoo import exceptions
from odoo.modules import module

if TYPE_CHECKING:
    from odoo.api import Environment
else:
    Environment = Any

_logger = logging.getLogger(__name__)


class InsufficientCreditError(Exception):
    data: dict[str, Any]


class IAPServerError(Exception):
    pass


def jsonrpc(
    url: str,
    method: str = "call",
    params: dict[str, Any] | None = None,
    timeout: float = 15,
    *,
    env: Environment,
    purpose: str | None = None,
) -> Any:
    if module.current_test:
        raise exceptions.AccessError("Unavailable during tests.")  # noqa: E8505 -- a guard against reaching IAP from a test run

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": uuid.uuid4().hex,
    }

    _logger.info("iap jsonrpc %s", url)
    egress: Any = env["ir.egress"]
    try:
        with egress.session(purpose=purpose or "iap", policy="private") as session:
            req = session.post(url, json=payload, timeout=timeout)
        req.raise_for_status()
        response = req.json()
        _logger.info(
            "iap jsonrpc %s responded in %.3f seconds", url, req.elapsed.total_seconds()
        )
        if "error" in response:
            error_data = response["error"].get("data") or {}
            name = (error_data.get("name") or "").rpartition(".")[-1]
            if name == "InsufficientCreditError":
                credit_error = InsufficientCreditError(error_data.get("message"))
                credit_error.data = error_data
                raise credit_error
            raise IAPServerError("An error occurred on the IAP server")
        return response.get("result")
    except requests.exceptions.Timeout as err:
        _logger.warning("iap jsonrpc %s timed out", url)
        raise exceptions.AccessError(
            env._(
                "The request to the service timed out. Please contact the author of the app. The URL it tried to contact was %s",
                url,
            )
        ) from err
    except (requests.exceptions.RequestException, IAPServerError) as e:
        _logger.warning("iap jsonrpc %s failed, %s: %s", url, e.__class__.__name__, e)
        raise exceptions.AccessError(
            env._(
                "An error occurred while reaching %s. Please contact Odoo support if this error persists.",
                url,
            )
        ) from e

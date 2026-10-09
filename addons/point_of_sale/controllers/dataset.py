import logging
from typing import Any
from uuid import UUID

from odoo import api, http
from odoo.http import ParameterError, request

from odoo.addons.web.controllers.dataset import DataSet

_logger = logging.getLogger(__name__)

OPERATION_CONTEXT_KEY = "pos_operation_uuid"


class PosDataSet(DataSet):
    @http.route()
    def call_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any],
        path: str | None = None,
    ) -> Any:
        context = kwargs.get("context") if isinstance(kwargs, dict) else None
        if not isinstance(context, dict) or OPERATION_CONTEXT_KEY not in context:
            return super().call_kw(model, method, args, kwargs, path=path)
        context = dict(context)
        operation_uuid = context.pop(OPERATION_CONTEXT_KEY)
        kwargs = {**kwargs, "context": context}
        call_kw = super().call_kw
        Operation = request.env["pos.processed.operation"]
        if not operation_uuid:
            return call_kw(model, method, args, kwargs, path=path)
        if not Operation._is_queueable(model, method):
            if not api.is_readonly(request.registry[model], method):
                _logger.warning(
                    "%s sent on %s.%s, which is not queueable: ran it without "
                    "deduplication. Mark the method @pos_queueable if the POS "
                    "client queues it.",
                    OPERATION_CONTEXT_KEY,
                    model,
                    method,
                )
            return call_kw(model, method, args, kwargs, path=path)
        try:
            operation_uuid = str(UUID(operation_uuid))
        except (TypeError, ValueError, AttributeError) as e:
            raise ParameterError(f"{OPERATION_CONTEXT_KEY} must be a UUID") from e
        return Operation._call_once(
            operation_uuid,
            model,
            method,
            args,
            kwargs,
            lambda: call_kw(model, method, args, kwargs, path=path),
        )

from typing import Any
from uuid import UUID

from odoo import http
from odoo.http import ParameterError, request

from odoo.addons.web.controllers.dataset import DataSet

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
        context = kwargs.get("context")
        if not isinstance(context, dict) or OPERATION_CONTEXT_KEY not in context:
            return super().call_kw(model, method, args, kwargs, path=path)
        context = dict(context)
        operation_uuid = context.pop(OPERATION_CONTEXT_KEY)
        kwargs = {**kwargs, "context": context}
        call_kw = super().call_kw
        if not operation_uuid or request.env.cr.readonly:
            return call_kw(model, method, args, kwargs, path=path)
        try:
            operation_uuid = str(UUID(operation_uuid))
        except (TypeError, ValueError, AttributeError) as e:
            raise ParameterError(f"{OPERATION_CONTEXT_KEY} must be a UUID") from e
        return request.env["pos.processed.operation"]._call_once(
            operation_uuid,
            model,
            method,
            lambda: call_kw(model, method, args, kwargs, path=path),
        )

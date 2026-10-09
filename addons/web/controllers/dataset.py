from typing import Any

from odoo import api, http
from odoo.http import NotFound, ParameterError, request
from odoo.libs.debug_log import DebugLog
from odoo.libs.worker_thread import current_worker_thread
from odoo.service.model import call_kw

from .utils import clean_action

_debug = DebugLog(__name__)


def _tag_thread_with_rpc_target(model: str, method: str, path: str | None) -> None:
    if path != f"{model}/{method}":
        current_worker_thread().rpc_model_method = f"{model}.{method}"


def _get_called_model(model: str) -> Any:
    if model not in request.env.registry:
        _debug.logic("rpc_unknown_model", model=model)
        raise NotFound
    return request.env[model]


class DataSet(http.Controller):
    def _call_kw_readonly(self, rule: Any, args: Any) -> bool:
        try:
            params = request.get_json_data()["params"]
            model_name, method_name = params["model"], params["method"]
        except (KeyError, TypeError) as e:
            _debug.logic("rpc_readonly_probe_malformed", error=repr(e))
            raise ParameterError(
                "call_kw expects params with a model and a method"
            ) from e
        if not isinstance(model_name, str) or not isinstance(method_name, str):
            _debug.logic("rpc_readonly_probe_not_strings")
            raise ParameterError("call_kw expects the model and method as strings")
        if not isinstance(params.get("args", []), list) or not isinstance(
            params.get("kwargs", {}), dict
        ):
            _debug.logic("rpc_readonly_probe_malformed_arguments")
            raise ParameterError(
                "call_kw expects args as a list and kwargs as an object"
            )
        try:
            model_class = request.registry[model_name]
        except KeyError:
            # This runs before authentication: answering NotFound here told an
            # anonymous caller which models exist. The endpoint refuses it once
            # the caller is authenticated (_get_called_model).
            _debug.logic("rpc_readonly_probe_unknown_model", model=model_name)
            return True
        readonly = api.is_readonly(model_class, method_name)
        _debug.logic(
            "rpc_readonly", model=model_name, method=method_name, readonly=readonly
        )
        return readonly

    @http.route(
        ["/web/dataset/call_kw", "/web/dataset/call_kw/<path:path>"],
        type="jsonrpc",
        auth="user",
        readonly=_call_kw_readonly,
    )
    def call_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any],
        path: str | None = None,
    ) -> Any:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "call_kw",
                model=model,
                method=method,
                args=len(args),
                kwargs=sorted(kwargs),
                path_match=path == f"{model}/{method}",
            )
        _tag_thread_with_rpc_target(model, method, path)
        with _debug.perf("call_kw", cr=request.env.cr, model=model, method=method):
            return call_kw(_get_called_model(model), method, args, kwargs)

    @http.route(
        ["/web/dataset/call_button", "/web/dataset/call_button/<path:path>"],
        type="jsonrpc",
        auth="user",
        readonly=_call_kw_readonly,
    )
    def call_button(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any],
        path: str | None = None,
    ) -> dict[str, Any] | bool:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "call_button",
                model=model,
                method=method,
                args=len(args),
                kwargs=sorted(kwargs),
            )
        _tag_thread_with_rpc_target(model, method, path)
        with _debug.perf("call_button", cr=request.env.cr, model=model, method=method):
            action = call_kw(_get_called_model(model), method, args, kwargs)
        if isinstance(action, dict) and action.get("type") != "":
            _debug.pipeline(
                "call_button_action",
                model=model,
                method=method,
                action_type=action.get("type"),
            )
            return clean_action(action, env=request.env)
        _debug.logic(
            "call_button_no_action",
            model=model,
            method=method,
            result_type=type(action).__name__,
        )
        return False

from typing import Any

from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import BadRequest, Controller, ParameterError, request, route
from odoo.libs.debug_log import DebugLog
from odoo.tools.safe_eval import safe_eval

from .utils import clean_action, get_model

_debug = DebugLog(__name__)


class MissingActionError(UserError):
    pass


def _views_request(
    action: dict[str, Any],
    context: dict[str, Any],
    view_context: dict[str, Any],
    view_options: dict[str, Any],
) -> dict[str, Any] | None:
    if action.get("type") != "ir.actions.act_window" or not action.get("res_model"):
        return None
    if action.get("embedded_action_ids") or view_context.get(
        "current_embedded_action_id"
    ):
        return None
    action_context = action.get("context") or {}
    if isinstance(action_context, str):
        try:
            action_context = safe_eval(action_context, {**context, "context": context})
        except ValueError, SyntaxError, ArithmeticError, TypeError:
            return None
    merged = {**view_context, **action_context}
    views = [[view_id, view_type] for view_id, view_type in action.get("views") or []]
    has_search = False
    if all(view_type in ("form", "search") for _id, view_type in views):
        views = [view for view in views if view[1] == "form"]
    else:
        search_view = action.get("search_view_id")
        if isinstance(search_view, int):
            search_view_id = search_view
        else:
            search_view_id = search_view[0] if search_view else False
        declared = [view for view in views if view[1] == "search"]
        if not declared:
            views.append([search_view_id, "search"])
        else:
            if search_view:
                declared[0][0] = search_view_id
            views = [
                view for view in views if view[1] != "search" or view is declared[0]
            ]
        has_search = True
    if not views:
        return None
    load_action_menus = (
        action.get("target") != "new" and action["res_model"] != "res.config.settings"
    )
    options: dict[str, Any] = {
        "action_id": action.get("id") or False,
        "embedded_action_id": False,
        "embedded_parent_res_id": False,
        "load_filters": has_search,
        "toolbar": bool(not merged.get("disable_toolbar") and load_action_menus),
        "arch": False,
    }
    if view_options.get("mobile"):
        options["mobile"] = True
    if view_options.get("debug"):
        options["debug"] = True
    return {
        "model": action["res_model"],
        "views": views,
        "context": {
            key: value
            for key, value in merged.items()
            if key == "lang" or key.endswith("_view_ref")
        },
        "options": options,
    }


def _with_views(
    action: dict[str, Any],
    context: dict[str, Any] | None,
    view_context: dict[str, Any] | None,
    view_options: dict[str, Any],
    views_known: dict[str, Any] | None,
) -> dict[str, Any]:
    views_request = _views_request(
        action, context or {}, view_context or {}, view_options
    )
    if views_request is None:
        return action
    if views_request == views_known:
        return {"action": action, "views_request": views_request}
    try:
        views = (
            request.env[views_request["model"]]
            .with_context(**views_request["context"])
            .get_views(views_request["views"], views_request["options"])
        )
    except AccessError, MissingError, UserError, ValueError, KeyError:
        _debug.logic("action_views_skipped", model=views_request["model"])
        return action
    return {"action": action, "views_request": views_request, "views": views}


class Action(Controller):
    @route("/web/action/load", type="jsonrpc", auth="user", readonly=True)
    def load(
        self,
        action_id: int | str,
        context: dict[str, Any] | None = None,
        view_options: dict[str, Any] | None = None,
        view_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | bool:
        action = self._load(action_id, context)
        if view_options is None or not isinstance(action, dict):
            return action
        return _with_views(action, context, view_context, view_options, None)

    def _load(
        self, action_id: int | str, context: dict[str, Any] | None
    ) -> dict[str, Any] | bool:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "action_load", action_id=action_id, context_keys=sorted(context or {})
            )
        if context:
            request.update_context(**context)
        Actions = request.env["ir.actions.actions"]
        resolved_by_name = False
        try:
            action_id = int(action_id)
        except TypeError, ValueError:
            try:
                if "." in action_id:
                    _debug.logic("action_load_resolve", action_id=action_id, by="xmlid")
                    action = request.env.ref(action_id)
                    if not action._name.startswith("ir.actions."):
                        msg = "Not an action"
                        raise ValueError(msg)
                else:
                    _debug.logic("action_load_resolve", action_id=action_id, by="path")
                    action = Actions._get_action_by_path(action_id)
                    if not action:
                        msg = "Action not found"
                        raise ValueError(msg)
                _debug.pipeline(
                    "action_load_resolved", action_id=action_id, action=action
                )
                action_id = action.id
                resolved_by_name = True
            except (
                TypeError,
                ValueError,
                KeyError,
                AttributeError,
                MissingError,
            ) as exc:
                _debug.logic(
                    "action_load_unresolved",
                    action_id=action_id,
                    error=type(exc).__name__,
                )
                raise MissingActionError(
                    request.env._("The action '%s' does not exist", action_id)
                ) from exc

        action = Actions.sudo().browse(action_id)._get_concrete()
        if action._name == Actions._name or (
            not resolved_by_name and not action.exists()
        ):
            _debug.logic("action_load_no_concrete_row", action_id=action_id)
            raise MissingActionError(
                request.env._("The action '%s' does not exist", action_id)
            )
        action_type = action._name
        env = request.env
        if action_type == "ir.actions.report":
            _debug.logic("action_load_report_bin_size", action_id=action_id)
            env = env(context=dict(env.context, bin_size=True))
        try:
            action.with_env(env)._check_access_to_load()
        except AccessError as exc:
            _debug.logic("action_load_refused", action_id=action_id, uid=env.uid)
            raise MissingActionError(
                request.env._("The action '%s' does not exist", action_id)
            ) from exc
        with _debug.perf(
            "action_load_dict",
            cr=env.cr,
            action_id=action_id,
            action_type=action_type,
        ):
            result = clean_action(
                action.with_env(env).sudo()._get_action_dict(), env=env
            )
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "action_load_result",
                action_id=action_id,
                action_type=action_type,
                keys=sorted(result),
            )
        return result

    @route("/web/action/run", type="jsonrpc", auth="user")
    def run(
        self,
        action_id: int,
        context: dict[str, Any] | None = None,
        view_options: dict[str, Any] | None = None,
        view_context: dict[str, Any] | None = None,
        views_known: dict[str, Any] | None = None,
    ) -> dict[str, Any] | bool:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "action_run", action_id=action_id, context_keys=sorted(context or {})
            )
        if context:
            request.update_context(**context)
        action = request.env["ir.actions.server"].browse([action_id])
        with _debug.perf("action_run", cr=request.env.cr, action_id=action_id):
            result = action.run()
        _debug.logic(
            "action_run_result",
            action_id=action_id,
            result=result.get("type") if isinstance(result, dict) else bool(result),
        )
        if not result:
            return False
        cleaned = clean_action(result, env=action.env)
        if view_options is None or not isinstance(cleaned, dict):
            return cleaned
        return _with_views(cleaned, context, view_context, view_options, views_known)

    @route(
        "/web/action/load_breadcrumbs",
        type="jsonrpc",
        auth="user",
        readonly=True,
    )
    def load_breadcrumbs(self, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(actions, list) or not all(
            isinstance(action, dict) for action in actions
        ):
            _debug.logic("breadcrumbs_actions_malformed")
            raise ParameterError("actions must be a list of objects")
        _debug.lifecycle("breadcrumbs_load", actions=len(actions))
        results = []
        with _debug.perf("breadcrumbs_load", cr=request.env.cr, actions=len(actions)):
            for idx, action in enumerate(actions):
                next_action = actions[idx + 1] if idx + 1 < len(actions) else None
                try:
                    results.append(self._get_breadcrumb(action, idx, next_action))
                except (MissingActionError, MissingError, AccessError) as exc:
                    _debug.logic(
                        "breadcrumb_error", index=idx, error=type(exc).__name__
                    )
                    results.append({"error": str(exc)})
        if _debug.perf.enabled:
            _debug.perf.count(
                "breadcrumbs_results",
                results=len(results),
                errors=sum(1 for r in results if "error" in r),
            )
        return results

    def _get_breadcrumb(
        self, action: dict[str, Any], idx: int, next_action: dict[str, Any] | None
    ) -> dict[str, Any]:
        record_id = action.get("resId")
        if action.get("action"):
            _debug.logic(
                "breadcrumb_by_action",
                index=idx,
                action=action.get("action"),
                res_id=record_id,
            )
            return self._get_action_breadcrumb(action, record_id, idx, next_action)
        if action.get("model"):
            _debug.logic(
                "breadcrumb_by_model",
                index=idx,
                model=action.get("model"),
                res_id=record_id,
            )
            Model = get_model(request.env, action["model"])
            if not record_id:
                msg = "Actions with a model should also have a resId"
                raise BadRequest(msg)
            if record_id == "new":
                return {"display_name": request.env._("New")}
            return {"display_name": Model.browse(record_id).display_name}
        _debug.logic("breadcrumb_unresolvable", index=idx)
        msg = "Actions should have either an action (id or path) or a model"
        raise BadRequest(msg)

    def _get_action_breadcrumb(
        self,
        action: dict[str, Any],
        record_id: Any,
        idx: int,
        next_action: dict[str, Any] | None,
    ) -> dict[str, Any]:
        act = self.load(action.get("action"))

        if act["type"] == "ir.actions.server":
            if not act["path"]:
                _debug.logic("breadcrumb_server_action_without_path", index=idx)
                return {"error": "A server action must have a path to be restored"}
            _debug.pipeline(
                "breadcrumb_server_action_run", index=idx, action_id=act["id"]
            )
            act = request.env["ir.actions.server"].browse(act["id"]).run()
            if not isinstance(act, dict):
                _debug.logic("breadcrumb_server_action_not_restorable", index=idx)
                return {"error": "Server action did not return a restorable action"}

        if not act.get("display_name"):
            act["display_name"] = act["name"]

        if (
            act["type"] == "ir.actions.client"
            and next_action is not None
            and action.get("action") == next_action.get("action")
        ):
            _debug.logic("breadcrumb_repeated_client_action", index=idx)
            return {"error": "Client actions don't have multi-record views"}

        if record_id:
            if record_id == "new":
                return {"display_name": request.env._("New")}
            if act.get("res_model"):
                _debug.logic(
                    "breadcrumb_record_name",
                    index=idx,
                    model=act["res_model"],
                    res_id=record_id,
                )
                return {
                    "display_name": get_model(request.env, act["res_model"])
                    .browse(record_id)
                    .display_name
                }
            return {"display_name": act["display_name"]}

        if act.get("res_model") and act["type"] != "ir.actions.client":
            get_model(request.env, act["res_model"]).check_access("read")
            name = (
                act["display_name"]
                if any(view[1] not in ("form", "search") for view in act["views"])
                else None
            )
            _debug.logic(
                "breadcrumb_multi_record_views",
                index=idx,
                multi_record=name is not None,
                name=name,
            )
        else:
            name = act["display_name"]
        return {"display_name": name}

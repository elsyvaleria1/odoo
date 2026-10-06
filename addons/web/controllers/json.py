import ast
from datetime import date
from http import HTTPStatus
from typing import Any
from urllib.parse import urlencode

import psycopg.errors
from lxml import etree

from odoo import http
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.http import BadRequest, NotFound, Response, request
from odoo.libs.debug_log import DebugLog
from odoo.tools.safe_eval import safe_eval

from .json_helpers import (
    get_domain_date,
    get_domain_default_filter,
    get_groupby,
    get_view_id_and_type,
)
from .utils import get_action_triples

_debug = DebugLog(__name__)


class WebJsonController(http.Controller):
    @http.route("/json/<path:subpath>", auth="user", type="http", readonly=True)
    def web_json(self, subpath: str, **kwargs: str) -> Response:
        _debug.lifecycle("json_unversioned_redirect", subpath=subpath)
        self._check_json_route_active()
        return request.redirect(
            f"/json/1/{subpath}?{urlencode(kwargs)}",
            HTTPStatus.TEMPORARY_REDIRECT,
        )

    @http.route(
        "/json/1/<path:subpath>", auth="bearer", type="http", readonly=True, typed=True
    )
    def web_json_1(self, subpath: str, **kwargs: str) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle("json_request", subpath=subpath, params=sorted(kwargs))
        self._check_json_route_active()
        if not request.env.user.has_group("base.group_allow_export"):
            _debug.logic("json_refused_no_export_group", subpath=subpath)
            raise AccessError(
                request.env._("You need export permissions to use the /json route")
            )

        env = request.env
        with _debug.perf("json_action_resolve", cr=env.cr, subpath=subpath):
            action, context, eval_context, record_id = self._get_action(subpath)
        model = env[action.res_model].with_context(context)

        view_type = kwargs.get("view_type")
        if not view_type and record_id:
            view_type = "form"
        view_id, view_type = get_view_id_and_type(action, view_type)
        with _debug.perf(
            "json_get_view",
            cr=env.cr,
            subpath=subpath,
            view_id=view_id,
            view_type=view_type,
        ):
            view = model.get_view(view_id, view_type)
        spec = model._get_fields_spec(view)
        _debug.pipeline(
            "json_resolved",
            subpath=subpath,
            action=action,
            model=model._name,
            view_id=view_id,
            view_type=view_type,
            record_id=record_id,
            spec_fields=len(spec),
        )

        if view_type == "form" or record_id:
            return self._get_json_record(model, spec, record_id)

        pinned: dict[str, str] = {}
        domains, pinned_domain = self._get_json_domains(
            model, action, context, eval_context, kwargs
        )
        pinned.update(pinned_domain)
        limit, offset, pinned_window = self._get_json_window(action, kwargs)
        pinned.update(pinned_window)

        view_tree = etree.fromstring(view["arch"])

        if env["ir.ui.view"]._view_type_has_date_range(view_type):
            _debug.logic("json_date_range_view", subpath=subpath, view_type=view_type)
            date_domain, pinned_dates = self._get_domain_json_date(view_tree, kwargs)
            domains.append(date_domain)
            pinned.update(pinned_dates)

        if view_type == "activity":
            _debug.logic("json_activity_view_extended", subpath=subpath)
            domains.append([("activity_ids", "!=", False)])
            self._update_json_activity_spec(model, spec)

        groupby, fields = get_groupby(
            view_tree, kwargs.get("groupby"), kwargs.get("fields")
        )
        self._check_json_groupby(model, groupby)
        aggregates = self._get_json_aggregates(model, fields)

        if groupby is not None and not kwargs.get("groupby"):
            pinned["groupby"] = ",".join(groupby)
            if "fields" not in kwargs and fields:
                pinned["fields"] = ",".join(fields)
        if groupby is None and fields:
            for field in fields:
                spec.setdefault(field, {})

        if pinned:
            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "json_pinned_redirect",
                    subpath=subpath,
                    pinned=sorted(pinned),
                    status=307,
                )
            encoded = urlencode({**kwargs, **pinned}, safe="()[], '\"")
            return request.redirect(
                f"/json/1/{subpath}?{encoded}", HTTPStatus.TEMPORARY_REDIRECT
            )
        _debug.pipeline(
            "json_listing",
            subpath=subpath,
            domains=len(domains),
            groupby=groupby,
            aggregates=aggregates,
            limit=limit,
            offset=offset,
        )
        return self._get_json_listing(
            model, Domain.AND(domains), spec, groupby, aggregates, limit, offset
        )

    def _get_json_record(
        self, model: Any, spec: dict[str, Any], record_id: int | None
    ) -> Response:
        if not record_id:
            _debug.logic("json_record_id_missing")
            raise BadRequest(request.env._("Missing record id"))
        with _debug.perf(
            "json_web_read", cr=model.env.cr, model=model._name, record_id=record_id
        ):
            res = model.browse(int(record_id)).web_read(spec)
        if not res:
            _debug.logic(
                "json_record_not_found", model=model._name, record_id=record_id
            )
            raise NotFound
        return request.prepare_json_response(res[0])

    def _get_json_listing(
        self,
        model: Any,
        domain: Domain,
        spec: dict[str, Any],
        groupby: list[str] | None,
        aggregates: list[str],
        limit: int,
        offset: int,
    ) -> Response:
        if groupby:
            with _debug.perf("json_web_read_group", cr=model.env.cr, model=model._name):
                res = model.web_read_group(
                    domain,
                    aggregates=aggregates,
                    groupby=groupby,
                    limit=limit,
                    offset=offset,
                )
            for value in res["groups"]:
                del value["__extra_domain"]
            _debug.perf.count(
                "json_groups",
                model=model._name,
                groups=len(res["groups"]),
                groupby=groupby,
            )
        else:
            with _debug.perf(
                "json_web_search_read", cr=model.env.cr, model=model._name
            ):
                res = model.web_search_read(
                    domain,
                    spec,
                    limit=limit,
                    offset=offset,
                )
            _debug.perf.count(
                "json_records",
                model=model._name,
                records=len(res.get("records", ())),
                length=res.get("length"),
            )
        res.pop("__version", None)
        return request.prepare_json_response(res)

    def _get_json_domains(
        self,
        model: Any,
        action: Any,
        context: dict[str, Any],
        eval_context: dict[str, Any],
        kwargs: dict[str, str],
    ) -> tuple[list, dict[str, str]]:
        pinned: dict[str, str] = {}
        domains = [safe_eval(action.domain or "[]", eval_context)]
        if "domain" in kwargs:
            try:
                user_domain = ast.literal_eval(kwargs.get("domain") or "[]")
            except (ValueError, SyntaxError) as exc:
                _debug.logic("json_user_domain_unparsable", error=type(exc).__name__)
                raise BadRequest(f"Invalid domain: {exc}") from exc
            _debug.logic("json_user_domain", terms=len(user_domain))
            domains.append(user_domain)
        else:
            default_domain = get_domain_default_filter(
                model, action, context, eval_context
            )
            if default_domain and not Domain(default_domain).is_true():
                _debug.logic("json_default_domain_pinned")
                pinned["domain"] = repr(list(default_domain))
            domains.append(default_domain)
        return domains, pinned

    def _get_json_window(
        self, action: Any, kwargs: dict[str, str]
    ) -> tuple[int, int, dict[str, str]]:
        try:
            limit = int(kwargs.get("limit", 0)) or action.limit
            offset = int(kwargs.get("offset", 0))
        except ValueError as exc:
            _debug.logic("json_window_unparsable", error=exc.args[0])
            raise BadRequest(exc.args[0]) from exc
        if limit < 0 or offset < 0:
            _debug.logic("json_window_negative", limit=limit, offset=offset)
            raise BadRequest("limit and offset must not be negative")
        pinned = {
            key: str(value)
            for key, value in (("offset", offset), ("limit", limit))
            if key not in kwargs
        }
        return limit, offset, pinned

    def _get_domain_json_date(
        self, view_tree: etree._Element, kwargs: dict[str, str]
    ) -> tuple[list, dict[str, str]]:
        start_date: date | None
        end_date: date | None
        try:
            start_date = date.fromisoformat(kwargs["start_date"])
            end_date = date.fromisoformat(kwargs["end_date"])
        except ValueError as exc:
            _debug.logic("json_date_range_unparsable", error=exc.args[0])
            raise BadRequest(exc.args[0]) from exc
        except KeyError:
            start_date = end_date = None
        try:
            date_domain = get_domain_date(start_date, end_date, view_tree)
        except ValueError as exc:
            _debug.logic("json_date_range_rejected", error=exc.args[0])
            raise BadRequest(exc.args[0]) from exc
        pinned: dict[str, str] = {}
        if "start_date" not in kwargs or "end_date" not in kwargs:
            pinned = {
                "start_date": date_domain[0][2].isoformat(),
                "end_date": date_domain[1][2].isoformat(),
            }
        return date_domain, pinned

    def _update_json_activity_spec(self, model: Any, spec: dict[str, Any]) -> None:
        added = 0
        for field_name, field in model._fields.items():
            if (
                field_name.startswith("activity_")
                and field_name not in spec
                and model._has_field_access(field, "read")
            ):
                spec[field_name] = {}
                added += 1
        _debug.logic("json_activity_spec", added=added)

    def _check_json_groupby(self, model: Any, groupby: list[str] | None) -> None:
        unknown = [
            spec
            for spec in groupby or ()
            if spec.split(":", 1)[0].split(".", 1)[0] not in model._fields
        ]
        if unknown:
            _debug.logic("json_groupby_unknown", model=model._name, unknown=unknown)
            raise BadRequest(
                request.env._(
                    "Unknown groupby fields for %(model)s: %(fields)s",
                    model=model._name,
                    fields=", ".join(unknown),
                )
            )

    def _get_json_aggregates(self, model: Any, fields: list[str] | None) -> list[str]:
        if not fields:
            return ["__count"]
        env = request.env
        invalid = [f for f in fields if ":" not in f and f not in model._fields]
        if invalid:
            _debug.logic("json_fields_unknown", model=model._name, unknown=invalid)
            raise BadRequest(
                env._(
                    "Unknown fields for %(model)s: %(fields)s",
                    model=model._name,
                    fields=", ".join(invalid),
                )
            )
        not_aggregatable = [
            f for f in fields if ":" not in f and model._fields[f].aggregator is None
        ]
        if not_aggregatable:
            _debug.logic(
                "json_fields_not_aggregatable",
                model=model._name,
                fields=not_aggregatable,
            )
            raise BadRequest(
                env._(
                    "Fields not aggregatable for %(model)s: %(fields)s",
                    model=model._name,
                    fields=", ".join(not_aggregatable),
                )
            )
        return [
            f"{fname}:{model._fields[fname].aggregator}" if ":" not in fname else fname
            for fname in fields
        ]

    def _check_json_route_active(self) -> None:
        sudo_env = request.env(su=True)
        if not (
            sudo_env.ref("base.module_base").demo
            or sudo_env["ir.config_parameter"].get_param("web.json.enabled")
        ):
            _debug.logic("json_route_inactive")
            raise NotFound

    def _get_action(
        self, subpath: str
    ) -> tuple[Any, dict[str, Any], dict[str, Any], int | None]:
        def get_action_triples_():
            try:
                yield from get_action_triples(request.env, subpath, start_pos=1)
            except ValueError as exc:
                raise BadRequest(exc.args[0]) from exc

        context = dict(request.env.context)
        active_id, action, record_id = list(get_action_triples_())[-1]
        action = action.sudo()
        if action.usage == "ir_actions_server" and action.path:
            _debug.pipeline(
                "json_server_action_readonly_run", subpath=subpath, action=action
            )
            try:
                with action.pool.cursor(readonly=True) as ro_cr:
                    if not ro_cr.readonly:
                        _debug.logic("json_readonly_enforced", subpath=subpath)
                        ro_cr.enforce_readonly()
                    action_data = action.with_env(action.env(cr=ro_cr, su=False)).run()
            except psycopg.errors.ReadOnlySqlTransaction as e:
                _debug.logic("json_server_action_write", subpath=subpath, wrapped=False)
                raise AccessError(action.env._("Unsupported server action")) from e
            except ValueError as e:
                if "ReadOnlySqlTransaction" not in str(e):
                    raise
                _debug.logic("json_server_action_write", subpath=subpath, wrapped=True)
                raise AccessError(action.env._("Unsupported server action")) from e
            if not isinstance(action_data, dict) or not action_data.get("type"):
                _debug.logic("json_server_action_no_action", subpath=subpath)
                raise BadRequest(
                    action.env._("The server action %s returns no action.", action.path)
                )
            action = action.env[action_data["type"]]
            action = action.new(
                action_data, origin=action.browse(action_data.pop("id", None))
            )
            _debug.pipeline(
                "json_server_action_result", subpath=subpath, action=action._origin
            )
        if action._name != "ir.actions.act_window":
            _debug.logic(
                "json_action_unsupported", subpath=subpath, action_model=action._name
            )
            msg = f"{action._name} are not supported server-side"
            raise BadRequest(msg)
        eval_context = dict(
            action._prepare_eval_context(action),
            active_id=active_id,
            context=context,
            allowed_company_ids=request.env.user.company_ids.ids,
        )
        context.update(safe_eval(action.context, eval_context))
        return action, context, eval_context, record_id

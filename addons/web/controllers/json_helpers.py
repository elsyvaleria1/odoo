from collections import defaultdict
from datetime import date
from typing import Literal

from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo.fields import Domain
from odoo.http import BadRequest, request
from odoo.libs.debug_log import DebugLog
from odoo.models import is_valid_object_name
from odoo.tools.safe_eval import safe_eval

_debug = DebugLog(__name__)


def get_view_id_and_type(
    action, view_type: str | None
) -> tuple[int | Literal[False], str]:
    if action._name != "ir.actions.act_window":
        msg = f"Expected ir.actions.act_window, got {action._name}"
        raise TypeError(msg)
    view_modes = action.view_mode.split(",")
    if not view_type:
        view_type = view_modes[0]
        _debug.logic("view_type_defaulted", view_type=view_type)

    try:
        view_id = next(
            view_id
            for view_id, action_view_type in action.views
            if view_type == action_view_type
        )
    except StopIteration:
        if view_type not in view_modes:
            _debug.logic(
                "view_type_not_in_action",
                view_type=view_type,
                action=action,
                modes=view_modes,
            )
            raise BadRequest(
                request.env._(
                    "Invalid view type '%(view_type)s' for action id=%(action)s",
                    view_type=view_type,
                    action=action.id,
                )
            ) from None
        view_id = False
    _debug.logic("action_view", action=action, view_id=view_id, view_type=view_type)
    return view_id, view_type


def get_domain_default_filter(model, action, context, eval_context):
    for ir_filter in model.env["ir.filters"].get_filters(
        model._name, action._origin.id
    ):
        if ir_filter["is_default"]:
            _debug.logic(
                "default_filter", name=ir_filter.get("name"), model=model._name
            )
            try:
                default_domain = (
                    model.env["ir.filters"]
                    .browse(ir_filter["id"])
                    ._get_domain_evaluated()
                )
            except ValueError as exc:
                _debug.logic(
                    "default_filter_domain_unevaluable", domain=ir_filter["domain"]
                )
                raise BadRequest(
                    request.env._("Malformed stored filter domain: %s", exc)
                ) from exc
            break
    else:

        def get_search_default_domains():
            view_tree = None
            for key, value in context.items():
                if key.startswith("search_default_") and value:
                    filter_name = key[15:]
                    if not is_valid_object_name(filter_name):
                        raise ValueError(
                            f"Invalid default search filter name for {key}"
                        )
                    if view_tree is None:
                        _debug.logic(
                            "search_default_view_load",
                            search_view=action.search_view_id.id,
                        )
                        view = model.get_view(action.search_view_id.id, "search")
                        view_tree = etree.fromstring(view["arch"])
                    if (
                        element := next(
                            (
                                el
                                for el in view_tree.iterfind(".//filter")
                                if el.get("name") == filter_name
                            ),
                            None,
                        )
                    ) is not None:
                        if domain := element.attrib.get("domain"):
                            _debug.logic(
                                "search_default_filter",
                                filter_name=filter_name,
                                has_domain=True,
                            )
                            yield domain
                        else:
                            _debug.logic(
                                "search_default_filter",
                                filter_name=filter_name,
                                has_domain=False,
                            )
                    else:
                        _debug.logic(
                            "search_default_filter_missing", filter_name=filter_name
                        )

        default_domain = Domain.AND(
            safe_eval(domain, eval_context) for domain in get_search_default_domains()
        )
    return default_domain


def get_domain_date(start_date, end_date, view_tree):
    if not start_date or not end_date:
        start_date = date.today() + relativedelta(day=1)
        end_date = start_date + relativedelta(months=1)
        _debug.logic("date_range_defaulted", start=start_date, end=end_date)
    date_field = view_tree.attrib.get("date_start")
    if not date_field:
        _debug.logic("date_start_missing", view=view_tree.tag)
        msg = "Could not find the date field in the view"
        raise ValueError(msg)
    return [(date_field, ">=", start_date), (date_field, "<", end_date)]


def get_groupby(view_tree, groupby=None, fields=None):
    groupby = groupby.split(",") if groupby else None
    if fields:
        fields = fields.split(",")
    else:
        fields = None
    if groupby is not None:
        _debug.logic("groupby", source="explicit", groupby=groupby, fields=fields)
        return groupby, fields

    if view_tree.tag in ("pivot", "graph"):
        field_by_type = defaultdict(list)
        for element in view_tree.findall(r"./field"):
            field_name = element.attrib.get("name")
            if element.attrib.get("invisible", "") in ("1", "true"):
                field_by_type["invisible"].append(field_name)
            else:
                field_by_type[element.attrib.get("type", "normal")].append(field_name)
        groupby = [
            *field_by_type.get("row", ()),
            *field_by_type.get("col", ()),
            *field_by_type.get("normal", ()),
        ]
        if fields is None:
            fields = field_by_type.get("measure", [])
        _debug.logic("groupby", source=view_tree.tag, groupby=groupby, fields=fields)
        return groupby, fields
    if field := view_tree.attrib.get("default_group_by"):
        _debug.logic("groupby_default", view=view_tree.tag, field=field)
        return (None, [field])
    _debug.logic("groupby_none", view=view_tree.tag)
    return None, None

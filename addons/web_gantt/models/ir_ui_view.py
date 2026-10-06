from lxml import etree

from odoo import fields, models
from odoo.tools import safe_eval

from odoo.addons.base.models.ir_ui_view_arch import ElementHandler, register

GANTT_VALID_ATTRIBUTES = {
    "__validate__",  # ir.ui.view implementation detail
    "date_start",
    "date_stop",
    "default_scale",  # should be dropped -- tracked in t27957
    "default_range",
    "class",
    "js_class",
    "form_view_id",
    "kanban_view_id",
    "multi_create_view",
    "progress",
    "consolidation",
    "consolidation_max",
    "consolidation_exclude",
    "string",
    "create",
    "on_create",
    "cell_create",
    "edit",
    "delete",
    "plan",
    "default_group_by",
    "display_mode",
    "display_unavailability",
    "disable_drag_drop",
    "duration_field",
    "total_row",
    "scales",  # should be renamed to ranges -- tracked in t27957
    "thumbnails",
    "precision",
    "color",
    "decoration-secondary",
    "decoration-success",
    "decoration-info",
    "decoration-warning",
    "decoration-danger",
    "sample",
    "progress_bar",
    "dependency_field",
    "dependency_inverted_field",
    "pill_label",
    "groups_limit",
}


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(selection_add=[("gantt", "Gantt")])

    # What the client's scale table accepts, scale by scale; a key or a part
    # outside this used to be dropped without a word.
    _GANTT_CELL_PRECISIONS = {
        "day": ("full", "half", "quarter"),
        "week": ("full", "half"),
        "month": ("full", "half"),
        "year": ("full",),
    }

    def _check_gantt_precision(self, node, precision) -> None:
        try:
            values = safe_eval.safe_eval(precision)
        except ValueError, SyntaxError:
            values = None
        if not isinstance(values, dict):
            raise self._prepare_view_error(
                self.env._(
                    "Invalid precision '%s' in gantt: expected a dict", precision
                ),
                node,
            )
        for scale, spec in values.items():
            allowed = self._GANTT_CELL_PRECISIONS.get(scale)
            if allowed is None:
                raise self._prepare_view_error(
                    self.env._(
                        "Invalid precision scale '%(scale)s' in gantt; scales are %(scales)s",
                        scale=scale,
                        scales=", ".join(self._GANTT_CELL_PRECISIONS),
                    ),
                    node,
                )
            part = str(spec).partition(":")[2]
            if part not in allowed:
                raise self._prepare_view_error(
                    self.env._(
                        "Invalid precision '%(spec)s' for scale '%(scale)s' in gantt; parts are %(parts)s",
                        spec=spec,
                        scale=scale,
                        parts=", ".join(allowed),
                    ),
                    node,
                )

    def _get_view_info(self):
        return {
            "gantt": {"icon": "fa-solid fa-bars-progress", "date_range": True}
        } | super()._get_view_info()

    def _is_qweb_based_view(self, view_type) -> bool:
        return bool(view_type == "gantt" or super()._is_qweb_based_view(view_type))


@register("gantt")
class GanttHandler(ElementHandler):
    __slots__ = ()

    def check(self, view, node, name_manager, node_info):
        if not node_info["validate"]:
            return

        templates_count = 0
        for child in node.iterchildren(tag=etree.Element):
            if child.tag == "templates":
                if not templates_count:
                    templates_count += 1
                else:
                    msg = view.env._("Gantt view can contain only one templates tag")
                    raise view._prepare_view_error(msg, child)
            elif child.tag != "field":
                msg = view.env._(
                    "Gantt child can only be field or template, got %s", child.tag
                )
                raise view._prepare_view_error(msg, child)

        default_scale = node.get("default_scale")
        if default_scale:
            if default_scale not in ("day", "week", "month", "year"):
                raise view._prepare_view_error(
                    view.env._("Invalid default_scale '%s' in gantt", default_scale),
                    node,
                )
        default_range = node.get("default_range")
        if default_range:
            if default_range not in ("day", "week", "month", "quarter", "year"):
                raise view._prepare_view_error(
                    view.env._("Invalid default_range '%s' in gantt", default_range),
                    node,
                )
        precision = node.get("precision")
        if precision:
            view._check_gantt_precision(node, precision)
        display_mode = node.get("display_mode")
        if display_mode:
            if display_mode not in ("dense", "sparse"):
                raise view._prepare_view_error(
                    view.env._("Invalid display_mode '%s' in gantt", display_mode), node
                )
        attrs = set(node.attrib)
        if "date_start" not in attrs:
            msg = view.env._("Gantt must have a 'date_start' attribute")
            raise view._prepare_view_error(msg, node)

        if "date_stop" not in attrs:
            msg = view.env._("Gantt must have a 'date_stop' attribute")
            raise view._prepare_view_error(msg, node)

        for attribute in ("date_start", "date_stop"):
            field = name_manager.model._fields.get(node.get(attribute))
            if not field or field.type not in ("date", "datetime"):
                msg = view.env._(
                    "Invalid %(attribute)s '%(value)s' in gantt: not a date field of %(model)s",
                    attribute=attribute,
                    value=node.get(attribute),
                    model=name_manager.model._name,
                )
                raise view._prepare_view_error(msg, node)

        if "dependency_field" in attrs and "dependency_inverted_field" not in attrs:
            msg = view.env._(
                "Gantt must have a 'dependency_inverted_field' attribute once the 'dependency_field' is specified"
            )
            raise view._prepare_view_error(msg, node)

        remaining = attrs - GANTT_VALID_ATTRIBUTES
        if remaining:
            msg = view.env._(
                "Invalid attributes (%(invalid_attributes)s) in gantt view. Attributes must be in (%(valid_attributes)s)",
                invalid_attributes=remaining,
                valid_attributes=GANTT_VALID_ATTRIBUTES,
            )
            raise view._prepare_view_error(msg, node)

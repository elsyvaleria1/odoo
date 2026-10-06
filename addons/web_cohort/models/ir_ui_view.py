from odoo import fields, models
from odoo.tools import view_validation

from odoo.addons.base.models.ir_ui_view_arch import ElementHandler, register

view_validation.register_schema("cohort", "web_cohort/rng/cohort_view.rng")


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(selection_add=[("cohort", "Cohort")])

    def _get_view_info(self):
        return {
            "cohort": {"icon": "oi oi-view-cohort", "date_range": True}
        } | super()._get_view_info()


@register("cohort")
class CohortHandler(ElementHandler):
    __slots__ = ()

    def postprocess(self, view, node, name_manager, node_info) -> None:
        for additional_field in ("date_start", "date_stop"):
            if fnames := node.get(additional_field):
                name_manager.add_available_field(
                    node, fnames.split(".", 1)[0], node_info
                )

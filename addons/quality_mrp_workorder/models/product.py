from typing import TypedDict

from odoo import models
from odoo.fields import Domain
from odoo.tools import SQL

_OPERATION_BOM_DOMAIN = [
    "|",
    "|",
    ("operation_id", "=", False),
    ("bom_id", "=", False),
    ("bom_active", "=", True),
]


class QualityPointAction(TypedDict):
    context: dict[str, object]
    domain: Domain | list[object]


def _update_quality_point_action(action: QualityPointAction) -> None:
    action["context"].update({"search_default_quality_points": 1})
    action["domain"] = Domain.AND([action["domain"], _OPERATION_BOM_DOMAIN])


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_view_quality_control_points(self):
        action = super().action_view_quality_control_points()
        _update_quality_point_action(action)
        return action

    def action_see_quality_checks(self):
        action = super().action_see_quality_checks()
        action["context"].update({"search_default_quality_checks": 1})
        return action


class ProductProduct(models.Model):
    _inherit = "product.product"

    def action_view_quality_control_points(self):
        action = super().action_view_quality_control_points()
        _update_quality_point_action(action)
        return action

    def action_see_quality_checks(self):
        action = super().action_see_quality_checks()
        action["context"].update({"search_default_quality_checks": 1})
        return action

    def _additional_quality_point_where_clause(self):
        return SQL("""(
                operation_id IS NULL
                OR operation_id IN (
                    SELECT ope.id FROM mrp_routing_workcenter AS ope
                    INNER JOIN mrp_bom as bom ON ope.bom_id = bom.id
                    WHERE bom.active = 't'
                )
            )""")

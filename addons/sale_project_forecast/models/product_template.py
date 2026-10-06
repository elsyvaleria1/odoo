from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.depends("service_policy")
    def _compute_planning_enabled(self) -> None:
        templates_with_disabled_planning = self.filtered(
            lambda template: (
                template.service_policy in ["delivered_manual", "delivered_milestones"]
            )
        )
        _debug.logic(
            "planning_disabled_by_service_policy",
            templates=templates_with_disabled_planning,
        )
        templates_with_disabled_planning.planning_enabled = False
        super(
            ProductTemplate, self - templates_with_disabled_planning
        )._compute_planning_enabled()

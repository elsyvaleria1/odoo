import ast

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductTrace(models.Model):
    _inherit = "product.trace"

    quality_check_ids = fields.Many2many(
        comodel_name="quality.check",
        relation="product_trace_quality_check_rel",
        column1="product_trace_id",
        column2="quality_check_id",
        string="Quality Checks",
    )
    quality_alert_ids = fields.Many2many(
        comodel_name="quality.alert",
        relation="product_trace_quality_alert_rel",
        column1="product_trace_id",
        column2="quality_alert_id",
        string="Quality Alerts",
    )

    quality_check_qty = fields.Integer(
        compute="_compute_quality_check_qty",
        groups="quality.group_quality_user",
    )
    quality_alert_qty = fields.Integer(
        compute="_compute_quality_alert_qty",
        groups="quality.group_quality_user",
    )

    @api.depends("quality_check_ids")
    @api.depends_context("company")
    def _compute_quality_check_qty(self) -> None:
        _debug.perf.count("lot_quality_check_qty_compute", lots=self)
        for prod_lot in self:
            domain = Domain.AND(
                [
                    self._get_domain_quality_check(prod_lot),
                    [("company_id", "=", self.env.company.id)],
                ]
            )
            prod_lot.quality_check_qty = self.env["quality.check"].search_count(domain)

    def _get_domain_quality_check(self, prod_lot):
        return [("trace_ids", "in", prod_lot.ids)]

    def action_view_quality_checks(self):
        self.check_singleton()
        action_values = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "quality_control.quality_check_action_production_lot"
        )
        domain = (
            ast.literal_eval(action_values.get("domain"))
            if action_values.get("domain")
            else []
        )
        action_values["domain"] = Domain.AND(
            [domain, self._get_domain_quality_check(self)]
        )
        return action_values

    @api.depends("quality_alert_ids")
    @api.depends_context("company")
    def _compute_quality_alert_qty(self) -> None:
        _debug.perf.count("lot_quality_alert_qty_compute", lots=self)
        for prod_lot in self:
            prod_lot.quality_alert_qty = self.env["quality.alert"].search_count(
                [
                    ("trace_ids", "in", prod_lot.ids),
                    ("company_id", "=", self.env.company.id),
                ]
            )

    def action_lot_open_quality_alerts(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "quality_control.quality_alert_action_check"
        )
        action.update(
            {
                "domain": [("trace_ids", "=", self.id)],
                "context": {
                    "default_product_id": self.product_id.id,
                    "default_trace_id": self.id,
                    "default_company_id": self.company_id.id,
                },
            }
        )
        return action

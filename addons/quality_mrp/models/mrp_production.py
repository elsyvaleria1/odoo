from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    check_ids = fields.One2many(
        comodel_name="quality.check",
        inverse_name="production_id",
        string="Checks",
    )
    quality_check_todo = fields.Boolean(compute="_compute_check")
    quality_check_fail = fields.Boolean(compute="_compute_check")
    quality_alert_ids = fields.One2many(
        comodel_name="quality.alert",
        inverse_name="production_id",
        string="Alerts",
    )
    quality_alert_count = fields.Count(count_of="quality_alert_ids")

    @api.depends("check_ids.quality_state")
    def _compute_check(self) -> None:
        self.check_ids.fetch(["quality_state"])
        for production in self:
            states = set(production.check_ids.mapped("quality_state"))
            production.quality_check_todo = "none" in states
            production.quality_check_fail = "fail" in states

    def button_quality_alert(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_alert_action_check"
        )
        action["views"] = [(False, "form")]
        action["context"] = {
            "default_company_id": self.company_id.id,
            "default_product_id": self.product_id.id,
            "default_product_tmpl_id": self.product_id.product_tmpl_id.id,
            "default_production_id": self.id,
        }
        return action

    def pre_button_mark_done(self):
        res = super().pre_button_mark_done()
        if isinstance(res, dict) and res.get("type") == "ir.actions.act_window":
            return res
        is_qc_status_ok = self._is_quality_check_done()
        _debug.logic(
            "qc_gate",
            productions=self,
            passed=is_qc_status_ok,
            checks=len(self.check_ids),
        )
        if not is_qc_status_ok and self.env.context.get("from_wizard"):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": self.env._("You still need to do the quality checks!"),
                    "next": {"type": "ir.actions.act_window_close"},
                    "sticky": False,
                    "type": "warning",
                },
            }
        elif not is_qc_status_ok:
            raise UserError(self.env._("You still need to do the quality checks!"))
        return res

    def _is_quality_check_done(self) -> bool:
        return not any(self.mapped("quality_check_todo"))

    def open_quality_alert_mo(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_alert_action_check"
        )
        action["context"] = {
            "default_company_id": self.company_id.id,
            "default_product_id": self.product_id.id,
            "default_product_tmpl_id": self.product_id.product_tmpl_id.id,
            "default_production_id": self.id,
        }
        action["domain"] = [("id", "in", self.quality_alert_ids.ids)]
        action["views"] = [(False, "list"), (False, "form")]
        if self.quality_alert_count == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = self.quality_alert_ids.id
        return action

    def check_quality(self):
        self.check_singleton()
        checks = self.check_ids.filtered(lambda x: x.quality_state == "none")
        if checks:
            return checks.action_view_quality_check_wizard()
        return None

    def action_cancel(self):
        res = super().action_cancel()
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "qc_checks_dropped",
                productions=self,
                checks=self.sudo().check_ids.filtered(
                    lambda x: x.quality_state == "none"
                ),
            )
        self.sudo().mapped("check_ids").filtered(
            lambda x: x.quality_state == "none"
        ).unlink()
        return res

    def _action_confirm_mo_backorders(self) -> None:
        super()._action_confirm_mo_backorders()
        (self.move_raw_ids | self.move_finished_ids)._create_quality_checks_for_mo()

    def action_view_on_demand_quality_check(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_check_action_main"
        )
        action["views"] = [(False, "form")]
        action["context"] = {
            **self.env.context,
            "default_product_id": self.product_id.id
            if len(self.move_finished_ids) == 1
            else False,
            "default_production_id": self.id,
        }
        return action

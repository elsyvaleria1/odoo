from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class QualityPoint(models.Model):
    _inherit = "quality.point"

    @api.model
    def _get_domain_for_production(self, quality_points_domain):
        quality_points_domain = super()._get_domain_for_production(
            quality_points_domain
        )
        return Domain.AND((quality_points_domain, Domain("operation_id", "=", False)))

    @api.constrains("operation_id", "measure_frequency_type")
    def _check_measure_frequency_type(self) -> None:
        for point in self:
            if point.measure_frequency_type == "on_demand" and point.operation_id:
                raise ValidationError(
                    self.env._(
                        "The On-demand frequency is not possible with work order quality points."
                    )
                )


class QualityCheck(models.Model):
    _inherit = "quality.check"

    operation_id = fields.Many2one(related="point_id.operation_id")


    def do_measure(self):
        self.check_singleton()
        res = super().do_measure()
        if not self.workorder_id:
            return res
        next_res = self._next()
        if isinstance(next_res, dict):
            return next_res
        return {"next_check_id": next_res}

    def _next(self):
        self.check_singleton()
        result = super()._next()
        _debug.logic(
            "check_next",
            check=self.id,
            workorder=self.workorder_id.id,
            state=self.quality_state,
            by="failure_wizard"
            if self.quality_state == "fail"
            and (self.warning_message or self.failure_message)
            else "advance",
        )
        if self.quality_state == "fail" and (
            self.warning_message or self.failure_message
        ):
            return {
                "name": self.env._("Quality Check Failed"),
                "type": "ir.actions.act_window",
                "res_model": "wizard.quality.check.decide",
                "views": [
                    (
                        self.env.ref(
                            "quality_control.quality_check_wizard_form_failure"
                        ).id,
                        "form",
                    )
                ],
                "target": "new",
                "context": {
                    **self.env.context,
                    "default_check_ids": [self.id],
                    "default_current_check_id": self.id,
                    "default_test_type": self.test_type,
                    "default_failure_message": self.failure_message,
                    "default_warning_message": self.warning_message,
                },
                "next_check_id": result,
            }
        return result

    def _get_check_result(self):
        if self.test_type == "passfail":
            return (
                self.env._("Success")
                if self.quality_state == "pass"
                else self.env._("Failure")
            )
        if self.test_type == "measure":
            return f"{self.measure} {self.norm_unit}"
        return super()._get_check_result()

    def _check_to_unlink(self):
        self.check_singleton()
        return super()._check_to_unlink() and not self.workorder_id

    def action_pass_and_next(self) -> dict:
        _debug.lifecycle("check_pass_and_next", check=self.id)
        self.check_singleton()
        self.do_pass()
        return {"next_check_id": self._next()}

    def action_fail_and_next(self):
        self.check_singleton()
        _debug.lifecycle("check_fail_and_next", check=self.id)
        self.do_fail()
        result = self._next()
        return result if isinstance(result, dict) else {"next_check_id": result}

from ast import literal_eval

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class QualityPoint(models.Model):
    _inherit = "quality.point"

    worksheet_template_id = fields.Many2one(
        comodel_name="worksheet.template",
        string="Template",
        domain="[('res_model', '=', 'quality.check'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    # tech field used by quality_field_domain widget
    worksheet_model_name = fields.Char(
        related="worksheet_template_id.model_id.model",
        string="Model Name",
    )
    worksheet_success_conditions = fields.Char(string="Success Conditions")


class QualityCheck(models.Model):
    _inherit = "quality.check"

    worksheet_template_id = fields.Many2one(
        comodel_name="worksheet.template",
        string="Quality Template",
        compute="_compute_worksheet_template_id",
        store=True,
        readonly=False,
        domain="[('res_model', '=', 'quality.check'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    worksheet_count = fields.Integer(compute="_compute_worksheet_count")

    @api.depends("point_id")
    def _compute_worksheet_template_id(self) -> None:
        # This is what the `create` override that stood below did, one browse
        # per vals dict; the stored compute already runs on create.
        _debug.perf.count("worksheet_template_compute", checks=self)
        for check in self:
            if check.point_id and check.point_id.test_type == "worksheet":
                check.worksheet_template_id = check.point_id.worksheet_template_id

    @api.depends("worksheet_template_id")
    def _compute_worksheet_count(self) -> None:
        # Grouped by template: each template has its own `x_` model, so this
        # is one `_read_group` per distinct template rather than one
        # `search_count` per check.
        self.worksheet_count = 0
        for template, checks in self.grouped("worksheet_template_id").items():
            if not template:
                continue
            model = self.env[template.model_id.sudo().model]
            counts = dict(
                model._read_group(
                    [("x_quality_check_id", "in", checks.ids)],
                    ["x_quality_check_id"],
                    ["__count"],
                )
            )
            for check in checks:
                check.worksheet_count = counts.get(check, 0)

    def action_view_quality_check_wizard(self, current_check_id=None):
        check_ids = sorted(self.ids)
        check_id = self.browse(current_check_id or check_ids[0])
        if check_id.test_type == "worksheet":
            # in this case the worksheet will pop up, while the wizard will be in the background
            # to prevent code duplication
            action = check_id.action_quality_worksheet()
            quality_wizard = self.env["wizard.quality.check.decide"].create(
                {
                    "check_ids": check_ids,
                    "current_check_id": check_id.id,
                }
            )
            action["context"].update(
                {
                    "default_check_ids": check_ids,
                    "default_current_check_id": check_id.id,
                    "quality_wizard_id": quality_wizard.id,
                    "from_failure_form": False,
                }
            )
            return action
        return super().action_view_quality_check_wizard(current_check_id)

    def action_quality_worksheet(self):
        _debug.pipeline("worksheet_open", checks=self)
        self.check_singleton()
        action = self.worksheet_template_id.action_id.sudo().read()[0]
        # `limit=1`: the search was unbounded and `worksheet.id` on more than
        # one raises rather than opening a form.  A unique constraint on
        # `x_quality_check_id` means that cannot happen today -- measured --
        # so this is a guard, not a fix.  Newest first, matching the report.
        worksheet = self.env[self.worksheet_template_id.model_id.sudo().model].search(
            [("x_quality_check_id", "=", self.id)], limit=1, order="create_date DESC"
        )
        context = self.env["ir.actions.actions"]._eval_action_context(
            action.get("context", "{}")
        )
        action_name = self._get_check_action_name()
        action.update(
            {
                "name": action_name,
                "res_id": worksheet.id if worksheet else False,
                "views": [(False, "form")],
                "target": "new",
                "context": {
                    **context,
                    "edit": True,
                    "default_x_quality_check_id": self.id,
                },
            }
        )
        return action

    def action_worksheet_check(self):
        _debug.lifecycle("worksheet_check_submit", checks=self)
        self.check_singleton()
        if self.worksheet_count == 0:
            raise UserError(self.env._("Please fill in the worksheet."))
        quality_wizard_id = self.env.context.get("quality_wizard_id")
        if not quality_wizard_id:
            return {"type": "ir.actions.act_window_close"}
        quality_wizard = self.env["wizard.quality.check.decide"].browse(
            quality_wizard_id
        )
        domain = Domain(
            literal_eval(self.point_id.worksheet_success_conditions or "[]")
        )
        model = self.env[self.worksheet_template_id.model_id.model]
        if model.search_count(
            domain & Domain("x_quality_check_id", "=", self.id), limit=1
        ):
            return quality_wizard.do_pass()
        return quality_wizard.do_fail()

    def action_worksheet_discard(self):
        _debug.lifecycle("worksheet_check_discard", checks=self)
        quality_wizard_id = self.env.context.get("quality_wizard_id")
        if quality_wizard_id:
            quality_wizard = self.env["wizard.quality.check.decide"].browse(
                quality_wizard_id
            )
            return quality_wizard.action_generate_previous_window()
        return {"type": "ir.actions.act_window_close"}

    def action_generate_next_window(self):
        _debug.pipeline("worksheet_next_window", checks=self)
        quality_wizard_id = self.env.context.get("quality_wizard_id")
        if quality_wizard_id:
            quality_wizard = self.env["wizard.quality.check.decide"].browse(
                quality_wizard_id
            )
            return quality_wizard.action_generate_next_window()
        return {"type": "ir.actions.act_window_close"}

    def _is_pass_fail_applicable(self) -> bool:
        _debug.logic("worksheet_pass_fail_applicable", checks=self)
        return self.test_type == "worksheet" or super()._is_pass_fail_applicable()

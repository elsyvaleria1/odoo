from odoo import SUPERUSER_ID, api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import convert

_debug = DebugLog(__name__)


class HrAppraisal(models.Model):
    _inherit = "hr.appraisal"

    employee_feedback_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Asked Feedback",
    )
    survey_ids = fields.Many2many(
        comodel_name="survey.survey",
        help="Sent out surveys",
    )
    completed_survey_count = fields.Integer(compute="_compute_completed_survey_count")
    total_survey_count = fields.Integer(compute="_compute_total_survey_count")

    @api.depends("survey_ids", "survey_ids.user_input_ids.state")
    def _compute_completed_survey_count(self) -> None:
        grouped_data = self.env["survey.user_input"]._read_group(
            domain=[("state", "=", "done"), ("appraisal_id", "in", self.ids)],
            groupby=["appraisal_id"],
            aggregates=["__count"],
        )
        mapped_data = dict(grouped_data)

        for appraisal in self:
            appraisal.completed_survey_count = mapped_data.get(appraisal, 0)

    @api.depends("survey_ids")
    def _compute_total_survey_count(self) -> None:
        grouped_data = self.env["survey.user_input"]._read_group(
            domain=[("appraisal_id", "in", self.ids)],
            groupby=["appraisal_id"],
            aggregates=["__count"],
        )
        mapped_data = dict(grouped_data)

        for appraisal in self:
            appraisal.total_survey_count = mapped_data.get(appraisal, 0)

    def action_ask_feedback(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.hr.appraisal.send.feedback.survey",
            "target": "new",
            "name": self.env._("Ask Feedback"),
        }

    def action_view_survey_inputs(self) -> dict:
        self.check_singleton()
        view_id = self.env.ref(
            "hr_appraisal_survey.hr_appraisal_survey_user_input_view_tree",
            raise_if_not_found=False,
        )
        return {
            "type": "ir.actions.act_window",
            "view_mode": "list",
            "res_model": "survey.user_input",
            "target": "current",
            "name": self.env._("Feedback Surveys"),
            "views": [[view_id.id, "list"]],
            "domain": [("appraisal_id", "=", self.id)],
        }

    def _notify_answer_360_feedback(self) -> None:
        # posted as OdooBot on purpose: 360 feedback is answered by colleagues
        # and the acting user is whoever submitted it, so switching authorship
        # to sudo() would name the rater in the appraisal chatter
        _debug.pipeline("feedback_360_notified", appraisals=self)
        for appraisal in self.with_user(SUPERUSER_ID):
            body = self.env._(
                "A new 360 Feedback report has been completed for the appraisal of %(employee_name)s.",
                employee_name=appraisal.employee_id.name,
            )
            appraisal.message_post(
                body=body, subtype_xmlid="hr_appraisal_survey.mt_360_feedback"
            )

    def _load_demo_data(self) -> dict | None:
        super()._load_demo_data()
        convert.convert_file(
            self.env,
            "hr_appraisal_survey",
            "demo/scenarios/scenario_appraisal_demo.xml",
            None,
            mode="init",
        )
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

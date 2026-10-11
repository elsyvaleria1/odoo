from urllib.parse import urlencode as url_encode

from odoo import fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict


class SurveyUser_Input(models.Model):
    _inherit = "survey.user_input"
    _access_anchors = frozendict(
        {
            "appraisal_manager_user": models.Anchor(
                "appraisal_id.manager_ids.user_id", kind="owner"
            ),
            "owner": models.Anchor("survey_id.restrict_user_ids", shared=True),
        }
    )

    appraisal_id = fields.Many2one(
        comodel_name="hr.appraisal",
        index="btree_not_null",
    )
    requested_by_id = fields.Many2one(
        related="create_uid.partner_id",
        string="Requested by",
    )

    def action_view_survey_inputs(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Survey Feedback"),
            "type": "ir.actions.act_url",
            "target": "new",
            "url": "/survey/print/%s?%s"
            % (
                self.survey_id.access_token,
                url_encode({"answer_token": self.access_token, "review": True}),
            ),
        }

    def action_view_all_survey_inputs(self) -> dict:
        if len(self.appraisal_id) > 1:
            raise ValidationError(
                self.env._("You can't open the results of multiple appraisals at once.")
            )
        if len(self.survey_id) > 1:
            raise ValidationError(
                self.env._("You can't open the results of multiple surveys at once.")
            )
        if not self.survey_id:
            raise ValidationError(self.env._("No surveys found for this appraisal."))
        return {
            "type": "ir.actions.act_url",
            "name": self.env._("Survey Feedback"),
            "target": "new",
            "url": "/survey/results/%s?%s"
            % (
                self.survey_id.id,
                url_encode({"appraisal_id": self.appraisal_id.id}),
            ),
        }

    def action_view_appraisal_survey_results(self):
        survey_input_ids = self
        if not survey_input_ids:
            appraisal_id = self.env.context.get("active_id")
            if not appraisal_id:
                raise ValidationError(
                    self.env._("Select the feedback you want to see the results of.")
                )
            survey_input_ids = self.search([("appraisal_id", "=", appraisal_id)])
        survey_count = len(survey_input_ids.survey_id)
        if survey_count == 0:
            raise ValidationError(self.env._("No surveys found for this appraisal."))
        if survey_count == 1:
            return survey_input_ids.action_view_all_survey_inputs()
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.survey.user_input.view.result",
            "target": "new",
            "name": self.env._("Choose Survey"),
            "context": {
                "default_survey_input_ids": survey_input_ids.ids,
                "dialog_size": "medium",
            },
        }

    def action_ask_feedback(self) -> dict:
        if len(self.appraisal_id) > 1:
            raise ValidationError(
                self.env._("You can't ask feedback for multiple appraisals at once.")
            )
        if len(self.survey_id) > 1:
            raise ValidationError(
                self.env._("You can't select multiple feedback templates.")
            )
        appraisal_id = self.appraisal_id
        set_emails = {email for email in self.partner_id.mapped("email") if email}
        if appraisal_id.employee_feedback_ids:
            employee_ids = appraisal_id.employee_feedback_ids.filtered(
                lambda e: (
                    e.work_email in set_emails
                    or e.user_id.partner_id.email in set_emails
                )
            ).ids
        else:
            employee_ids = []
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.hr.appraisal.send.feedback.survey",
            "target": "new",
            "name": self.env._("Ask Feedback"),
            "context": {
                "default_appraisal_id": appraisal_id.id,
                "default_employee_ids": employee_ids,
                "default_survey_template_id": self.survey_id.id,
            },
        }

    def _mark_done(self):
        self.appraisal_id._notify_answer_360_feedback()
        return super()._mark_done()

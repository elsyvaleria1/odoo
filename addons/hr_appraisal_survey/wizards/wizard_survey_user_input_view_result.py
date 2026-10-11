from odoo import api, fields, models


class WizardSurveyUserInputViewResult(models.TransientModel):
    _name = "wizard.survey.user_input.view.result"
    _description = "Select survey type for an appraisal to show its results"

    survey_input_ids = fields.Many2many(
        comodel_name="survey.user_input",
        string="Survey Inputs",
        required=True,
    )
    allowed_survey_template_ids = fields.Many2many(
        comodel_name="survey.survey",
        compute="_compute_allowed_survey_template_ids",
    )
    survey_template_id = fields.Many2one(
        comodel_name="survey.survey",
        string="Survey",
        compute="_compute_survey_template_id",
        precompute=True,
        compute_sudo=False,
        store=True,
        readonly=False,
        required=True,
        domain="[('id', 'in', allowed_survey_template_ids)]",
    )

    @api.depends("survey_input_ids")
    def _compute_allowed_survey_template_ids(self) -> None:
        for wizard in self:
            wizard.allowed_survey_template_ids = wizard.survey_input_ids.survey_id

    @api.depends("allowed_survey_template_ids")
    def _compute_survey_template_id(self) -> None:
        for wizard in self:
            if not wizard.survey_template_id:
                wizard.survey_template_id = wizard.allowed_survey_template_ids[
                    :1
                ]._origin

    def action_see_results(self):
        self.check_singleton()
        return self.survey_input_ids.filtered(
            lambda s: s.survey_id == self.survey_template_id
        ).action_view_all_survey_inputs()

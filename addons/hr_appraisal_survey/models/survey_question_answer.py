from odoo import fields, models


class SurveyQuestionAnswer(models.Model):
    _inherit = "survey.question.answer"

    survey_id = fields.Many2one(
        comodel_name="survey.survey",
        related="question_id.survey_id",
    )

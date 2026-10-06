from odoo import fields, models


class EsgMetricToSurveyQuestion(models.Model):
    _name = "esg.metric.to.survey.question"
    _description = "Link the ESG metrics to the survey questions"
    _table = "esg_metric_to_survey_question_rel"

    metric_id = fields.Many2one(
        comodel_name="esg.metric",
        export_string_translation=False,
        index=True,
        required=True,
        ondelete="cascade",
    )
    question_id = fields.Many2one(
        comodel_name="survey.question",
        export_string_translation=False,
        index=True,
        required=True,
        ondelete="cascade",
    )
    metric_score_type = fields.Selection(
        selection=[
            ("impact", "Stakeholder Impact Severity"),
            ("financial", "Stakeholder Financial Severity"),
        ],
        required=True,
    )

    _check_no_duplicate = models.Constraint(
        "UNIQUE(metric_id, question_id)",
        "No duplicated (metric_id, question_id) pair is allowed.",
    )

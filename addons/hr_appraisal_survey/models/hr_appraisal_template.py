from odoo import fields, models


class HrAppraisalTemplate(models.Model):
    _inherit = "hr.appraisal.template"

    survey_template_ids = fields.Many2many(
        comodel_name="survey.survey",
        string="360 Feedback Survey",
        domain=[("survey_type", "=", "appraisal")],
        help="The survey templates available to choose from for the appraisals that use this template.",
    )

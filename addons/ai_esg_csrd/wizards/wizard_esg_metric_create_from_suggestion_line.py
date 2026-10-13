from odoo import fields, models


class WizardEsgMetricCreateFromSuggestionLine(models.TransientModel):
    _name = "wizard.esg.metric.create.from.suggestion.line"
    _description = "AI suggestion of ESG Metric"

    wizard_id = fields.Many2one(
        comodel_name="wizard.esg.metric.create.from.suggestion",
        required=True,
    )
    is_selected = fields.Boolean()
    esrs_id = fields.Many2one(
        comodel_name="esg.esrs",
        required=True,
    )
    code = fields.Char(related="esrs_id.code")
    name = fields.Char()
    type = fields.Selection(
        selection=[
            ("positive_impact", "Positive Impact"),
            ("negative_impact", "Negative Impact"),
            ("risk", "Risk"),
            ("opportunity", "Opportunity"),
        ],
        readonly=True,
        required=True,
    )
    category = fields.Selection(related="esrs_id.category")
    detail = fields.Text()

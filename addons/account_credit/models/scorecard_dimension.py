from odoo import fields, models

MEASURES = [
    ("dbt", "Days beyond terms, amount-weighted"),
    ("late_ratio", "Share of amount paid late"),
    ("max_days_late", "Worst delay in the window"),
    ("oldest_open_days", "Oldest open receivable, days past due"),
    ("tenure_months", "Months as a customer"),
    ("collateral_coverage", "Collateral over exposure, percent"),
    ("document_compliance", "Documents compliant (100) or not (0)"),
    ("bureau_score", "Credit bureau score, as reported"),
    ("z_score", "Altman Z'' score from the last financial statements"),
]


class ScorecardDimension(models.Model):
    _inherit = "scorecard.dimension"

    code = fields.Selection(
        selection_add=MEASURES,
        ondelete=dict.fromkeys([code for code, _label in MEASURES], "cascade"),
    )

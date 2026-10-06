from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    po_validation_level = fields.Selection(
        selection=[
            ("none", "No Validation - Auto-approve All"),
            ("manager_amount", "Manager Approval Above Threshold"),
            ("module_approval", "Advanced Approval Workflow"),
        ],
        string="Purchase Order Validation Level",
        default="none",
        required=True,
        help="""Define the validation workflow for purchase orders:

        • No Validation: All orders are auto-approved (not recommended)
        • Manager Approval Above Threshold: Orders above threshold require manager approval
        • Advanced Approval Workflow: Use sophisticated approval categories with custom rules

        Recommendation: Use 'Advanced Approval Workflow' for best control
        """,
    )
    po_validation_amount = fields.Monetary(
        string="Purchase Approval Threshold Amount",
        currency_field="currency_id",
        default=5000.0,
        help="Orders with total >= this amount require approval (only for 'Manager Approval Above Threshold' level)",
    )
    po_auto_confirm_on_approval = fields.Boolean(
        string="Purchase Auto-Confirm on Approval",
        default=True,
        help="Automatically confirm purchase orders when all required approvals are granted",
    )

    po_rate_limit_enabled = fields.Boolean(
        string="Enable Purchase Rate Limiter",
        default=True,
        help="When enabled, monitors for suspicious patterns of below-threshold orders. "
        "If limits are exceeded, approval is required even for managers.",
    )
    po_rate_limit_hours = fields.Integer(
        string="PO Rate Limit Time Window (Hours)",
        default=24,
        help="Time window in hours for rate limit calculations. Orders older than this are not counted.",
    )
    po_rate_limit_count = fields.Integer(
        string="PO Max Orders Below Threshold",
        default=5,
        help="Maximum number of below-threshold orders a user can create "
        "within the time window before approval is required.",
    )
    po_rate_limit_amount = fields.Monetary(
        string="PO Max Cumulative Amount Below Threshold",
        currency_field="currency_id",
        default=15000.0,
        help="Maximum cumulative amount of below-threshold orders within the time window before approval is required.",
    )

    _PO_RATE_LIMIT_FIELDS = (
        "po_rate_limit_hours",
        "po_rate_limit_count",
        "po_rate_limit_amount",
    )

    @api.constrains("po_rate_limit_enabled", *_PO_RATE_LIMIT_FIELDS)
    def _check_po_rate_limits(self) -> None:
        for company in self:
            if not company.po_rate_limit_enabled:
                continue
            for field_name in self._PO_RATE_LIMIT_FIELDS:
                if company[field_name] <= 0:
                    raise ValidationError(
                        self.env._(
                            "Set '%(label)s' above zero on '%(company)s', or untick "
                            "'Enable Purchase Rate Limiter'. A zero is not read as "
                            "'never allow this': the rate limiter substitutes its own "
                            "default and goes on permitting orders.",
                            label=self._fields[field_name].string,
                            company=company.display_name,
                        ),
                    )

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    so_validation_level = fields.Selection(
        selection=[
            ("none", "No Validation - Auto-approve All"),
            ("manager_amount", "Manager Approval Above Threshold"),
            ("module_approval", "Advanced Approval Workflow"),
        ],
        string="Sales Order Validation Level",
        default="none",
        required=True,
        help="""Define the validation workflow for sales orders:

        • No Validation: All orders are auto-approved (not recommended)
        • Manager Approval Above Threshold: Orders above threshold require manager approval
        • Advanced Approval Workflow: Use sophisticated approval categories with custom rules

        Recommendation: Use 'Advanced Approval Workflow' for best control
        """,
    )
    so_validation_amount = fields.Monetary(
        string="Sales Approval Threshold Amount",
        currency_field="currency_id",
        default=10000.0,
        help="Orders with total >= this amount require approval (only for 'Manager Approval Above Threshold' level)",
    )
    so_auto_confirm_on_approval = fields.Boolean(
        string="Sales Auto-Confirm on Approval",
        default=True,
        help="Automatically confirm sales orders when all required approvals are granted",
    )

    so_rate_limit_enabled = fields.Boolean(
        string="Enable Sales Rate Limiter",
        default=True,
        help="When enabled, monitors for suspicious patterns of below-threshold orders. "
        "If limits are exceeded, approval is required even for managers.",
    )
    so_rate_limit_hours = fields.Integer(
        string="SO Rate Limit Time Window (Hours)",
        default=24,
        help="Time window in hours for rate limit calculations. Orders older than this are not counted.",
    )
    so_rate_limit_count = fields.Integer(
        string="SO Max Orders Below Threshold",
        default=5,
        help="Maximum number of below-threshold orders a user can create "
        "within the time window before approval is required.",
    )
    so_rate_limit_amount = fields.Monetary(
        string="SO Max Cumulative Amount Below Threshold",
        currency_field="currency_id",
        default=30000.0,
        help="Maximum cumulative amount of below-threshold orders within the time window before approval is required.",
    )

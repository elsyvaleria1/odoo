from odoo import fields, models

from .credit_config import CREDIT_FOLDER_DOMAIN


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    credit_folder_id = fields.Many2one(
        comodel_name="document.document",
        related="company_id.credit_config_id.credit_folder_id",
        readonly=False,
        domain=CREDIT_FOLDER_DOMAIN,
        check_company=True,
    )
    credit_watch_days = fields.Integer(
        related="company_id.credit_config_id.watch_days",
        readonly=False,
    )
    credit_default_days = fields.Integer(
        related="company_id.credit_config_id.default_days",
        readonly=False,
    )
    credit_default_materiality_amount = fields.Float(
        related="company_id.credit_config_id.default_materiality_amount",
        readonly=False,
    )
    credit_exception_max_days = fields.Integer(
        related="company_id.credit_config_id.exception_max_days",
        readonly=False,
    )
    credit_metrics_window_months = fields.Integer(
        related="company_id.credit_config_id.metrics_window_months",
        readonly=False,
    )
    credit_auto_downgrade = fields.Boolean(
        related="company_id.credit_config_id.auto_downgrade",
        readonly=False,
    )
    credit_review_user_id = fields.Many2one(
        related="company_id.credit_config_id.review_user_id",
        readonly=False,
    )
    credit_provision_journal_id = fields.Many2one(
        related="company_id.credit_config_id.provision_journal_id",
        readonly=False,
    )
    credit_provision_expense_account_id = fields.Many2one(
        related="company_id.credit_config_id.provision_expense_account_id",
        readonly=False,
    )
    credit_provision_allowance_account_id = fields.Many2one(
        related="company_id.credit_config_id.provision_allowance_account_id",
        readonly=False,
    )
    credit_provision_matrix_id = fields.Many2one(
        related="company_id.credit_config_id.provision_matrix_id",
        readonly=False,
    )

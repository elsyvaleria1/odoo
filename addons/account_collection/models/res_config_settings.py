from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    collection_custody_days_cash = fields.Integer(
        related="company_id.account_config_id.collection_custody_days_cash",
        readonly=False,
    )
    collection_custody_days_check = fields.Integer(
        related="company_id.account_config_id.collection_custody_days_check",
        readonly=False,
    )
    collection_custody_limit = fields.Monetary(
        related="company_id.account_config_id.collection_custody_limit",
        currency_field="currency_id",
        readonly=False,
    )
    collection_send_receipt = fields.Boolean(
        related="company_id.account_config_id.collection_send_receipt",
        readonly=False,
    )
    collection_supervisor_id = fields.Many2one(
        related="company_id.account_config_id.collection_supervisor_id",
        readonly=False,
    )
    collection_shortage_account_id = fields.Many2one(
        related="company_id.account_config_id.collection_shortage_account_id",
        readonly=False,
    )
    collection_overage_account_id = fields.Many2one(
        related="company_id.account_config_id.collection_overage_account_id",
        readonly=False,
    )
    collection_check_fee_account_id = fields.Many2one(
        related="company_id.account_config_id.collection_check_fee_account_id",
        readonly=False,
    )
    collection_max_distance_km = fields.Float(
        related="company_id.account_config_id.collection_max_distance_km",
        readonly=False,
    )

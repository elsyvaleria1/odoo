from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_l10n_fr_hr_payroll = fields.Boolean(string="French Payroll")
    module_l10n_be_hr_payroll = fields.Boolean(string="Belgium Payroll")
    module_l10n_in_hr_payroll = fields.Boolean(string="Indian Payroll")
    module_hr_payroll_account_iso20022 = fields.Boolean(
        string="Payroll with SEPA payment"
    )
    payslip_generate_and_send_trigger = fields.Selection(
        selection=[
            ("on_confirmed", "When Confirmed"),
            ("on_paid", "When Paid"),
            ("never", "Manually"),
        ],
        string="Send Payslips to Employees",
        default="on_confirmed",
        config_parameter="hr_payroll.payslip_generate_and_send_trigger",
    )
    ytd_reset_day = fields.Integer(
        related="company_id.ytd_reset_day",
        readonly=False,
    )
    ytd_reset_month = fields.Selection(
        related="company_id.ytd_reset_month",
        readonly=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = (
                self.env["res.company"].browse(vals["company_id"])
                if vals.get("company_id")
                else self.env.company
            )
            ytd_reset_day = vals.pop("ytd_reset_day", False) or company.ytd_reset_day
            ytd_reset_month = (
                vals.pop("ytd_reset_month", False) or company.ytd_reset_month
            )
            vals = {}
            if ytd_reset_day != company.ytd_reset_day:
                vals["ytd_reset_day"] = ytd_reset_day
            if ytd_reset_month != company.ytd_reset_month:
                vals["ytd_reset_month"] = ytd_reset_month
            if vals:
                company.write(vals)
        return super().create(vals_list)

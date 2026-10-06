from datetime import timedelta

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardAccountConfigUpdateFiscalYear(models.TransientModel):
    _name = "wizard.account.config.update.fiscal.year"
    _description = "Opening Balance of Financial Year"

    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
    )
    opening_move_posted = fields.Boolean(compute="_compute_opening_move_posted")
    opening_date = fields.Date(
        related="company_id.account_config_id.account_opening_date",
        string="Opening Date",
        readonly=False,
        required=True,
        help="Date from which the accounting is managed in Odoo. It is the date of the opening entry.",
    )
    fiscalyear_last_day = fields.Integer(
        related="company_id.account_config_id.fiscalyear_last_day",
        readonly=False,
        required=True,
        help="The last day of the month will be used if the chosen day doesn't exist.",
    )
    fiscalyear_last_month = fields.Selection(
        related="company_id.account_config_id.fiscalyear_last_month",
        readonly=False,
        required=True,
        help="The last day of the month will be used if the chosen day doesn't exist.",
    )
    account_return_periodicity = fields.Selection(
        related="company_id.account_config_id.account_return_periodicity",
        string="Periodicity in month",
        readonly=False,
        required=True,
    )
    account_tax_return_journal_id = fields.Many2one(
        related="company_id.account_config_id.account_tax_return_journal_id",
        string="Journal",
        readonly=False,
    )
    account_return_reminder_day = fields.Integer(
        related="company_id.account_config_id.account_return_reminder_day",
        string="Reminder",
        readonly=False,
        required=True,
    )
    vat_label = fields.Char(related="company_id.country_id.vat_label")

    @api.depends("company_id.account_config_id.account_opening_move_id")
    def _compute_opening_move_posted(self) -> None:
        for record in self:
            record.opening_move_posted = record.company_id.opening_move_posted()

    @api.model
    def _company_fields_to_update(self) -> set:
        # The return settings trigger tax return generation: they go in the same
        # company write so that generation runs once.
        return {
            "fiscalyear_last_day",
            "fiscalyear_last_month",
            "opening_date",
            "account_return_periodicity",
            "account_tax_return_journal_id",
            "account_return_reminder_day",
        }

    @api.model
    def _update_company(self, company_id, vals) -> None:
        company_fields_to_update = {k: k for k in self._company_fields_to_update()}
        company_fields_to_update["opening_date"] = "account_opening_date"
        company_id.write(
            {
                company_field: vals[wizard_field]
                for wizard_field, company_field in company_fields_to_update.items()
                if wizard_field in vals
            }
        )
        opening_date = vals.get(
            "opening_date", company_id.account_config_id.account_opening_date
        )
        opening_move = company_id.account_config_id.account_opening_move_id
        if opening_date and opening_move.state == "draft":
            opening_move.write(
                {
                    "date": fields.Date.from_string(opening_date) - timedelta(days=1),
                }
            )

    @api.model_create_multi
    @_debug.perf.timed
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                model=self._name,
                count=len(vals_list),
                fields=sorted({key for vals in vals_list for key in vals}),
            )
        for vals in vals_list:
            if "company_id" in vals:
                company = self.env["res.company"].browse(vals["company_id"])
                _debug.logic("setup_company_fields_forwarded", company=company)
                self._update_company(company, vals)

                for key in self._company_fields_to_update():
                    vals.pop(key, None)

        return super().create(vals_list)

    @_debug.perf.timed
    def write(self, vals):
        _debug.lifecycle("write", records=self, fields=sorted(vals))
        for wiz in self:
            wiz._update_company(wiz.company_id, vals)

        for key in self._company_fields_to_update():
            vals.pop(key, None)

        return super().write(vals)

    @_debug.perf.timed
    def action_save_onboarding_fiscal_year(self):
        _debug.lifecycle("action_save_onboarding_fiscal_year", records=self)
        step_state = (
            self.env["onboarding.onboarding.step"]
            .with_company(self.company_id)
            .action_validate_step("account.onboarding_onboarding_step_fiscal_year")
        )
        if step_state == "JUST_DONE":
            self.env.ref(
                "account.onboarding_onboarding_account_dashboard"
            )._prepare_rendering_values()
        if self.env.context.get("open_account_return_on_save"):
            return self.env["account.return"].action_view_tax_return_view(
                self.env.context.get("additional_return_domain"),
                self.env.context.get("additional_return_context"),
            )
        return {"type": "ir.actions.client", "tag": "soft_reload"}

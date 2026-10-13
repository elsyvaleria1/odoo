from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class OnboardingOnboardingStep(models.Model):
    _inherit = "onboarding.onboarding.step"

    @api.model
    @_debug.perf.timed
    def action_view_step_company_data(self) -> dict:
        _debug.lifecycle("action_view_step_company_data", records=self)
        company = (
            self.env["account.journal"]
            .browse(self.env.context.get("journal_id", None))
            .company_id
            or self.env.company
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Set your company data"),
            "res_model": "res.company",
            "res_id": company.id,
            "views": [
                (self.env.ref("account.res_company_form_view_onboarding").id, "form")
            ],
            "target": "new",
        }

    @api.model
    @_debug.perf.timed
    def action_view_step_fiscal_year(self) -> dict:
        _debug.lifecycle("action_view_step_fiscal_year", records=self)
        company = (
            self.env["account.journal"]
            .browse(self.env.context.get("journal_id", None))
            .company_id
            or self.env.company
        )
        new_wizard = self.env["wizard.account.config.update.fiscal.year"].create(
            {"company_id": company.id}
        )
        view_id = self.env.ref("account.setup_financial_year_opening_form").id

        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Accounting Periods"),
            "view_mode": "form",
            "res_model": "wizard.account.config.update.fiscal.year",
            "target": "new",
            "res_id": new_wizard.id,
            "views": [[view_id, "form"]],
            "context": {
                "dialog_size": "medium",
            },
        }

    @api.model
    @_debug.perf.timed
    def action_view_step_chart_of_accounts(self) -> str | dict:
        _debug.lifecycle("action_view_step_chart_of_accounts", records=self)
        company = (
            self.env["account.journal"]
            .browse(self.env.context.get("journal_id", None))
            .company_id
            or self.env.company
        )
        self.sudo().with_company(company).action_validate_step(
            "account.onboarding_onboarding_step_chart_of_accounts"
        )

        if company.opening_move_posted():
            return "account.action_account_form"

        view_id = self.env.ref("account.init_accounts_tree").id
        domain = [
            *self.env["account.account"]._check_company_domain(company),
            ("account_type", "!=", "equity_unaffected"),
        ]
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Chart of Accounts"),
            "res_model": "account.account",
            "view_mode": "list",
            "limit": 99999999,
            "search_view_id": [self.env.ref("account.view_account_search").id],
            "views": [[view_id, "list"], [False, "form"]],
            "domain": domain,
        }

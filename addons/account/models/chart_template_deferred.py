from odoo import models, modules
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

SEPA_MODULES = ("account_iso20022", "account_bank_statement_import_camt")


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    def _get_deferred_res_company(self, chart_template) -> dict:
        company = self.env.company
        data = self._prepare_chart_template_data(chart_template)
        company_data = data["res.company"].get(company.id, {})

        required_data = {
            k: v for k, v in data.items() if k in ["account.journal", "account.account"]
        }
        self._pre_reload_data(company, data["template_data"], required_data)

        return {
            company.id: {
                "deferred_expense_journal_id": company.account_config_id.deferred_expense_journal_id.id
                or company_data.get("deferred_expense_journal_id"),
                "deferred_revenue_journal_id": company.account_config_id.deferred_revenue_journal_id.id
                or company_data.get("deferred_revenue_journal_id"),
                "deferred_expense_account_id": company.account_config_id.deferred_expense_account_id.id
                or company_data.get("deferred_expense_account_id"),
                "deferred_revenue_account_id": company.account_config_id.deferred_revenue_account_id.id
                or company_data.get("deferred_revenue_account_id"),
            }
        }

    @_debug.perf.timed
    def _prepare_chart_template_data(self, chart_template):
        data = super()._prepare_chart_template_data(chart_template)

        for company_data in data["res.company"].values():
            company_data["deferred_expense_journal_id"] = company_data.get(
                "deferred_expense_journal_id"
            ) or next(
                (
                    xid
                    for xid, d in data["account.journal"].items()
                    if d["type"] == "general"
                ),
                None,
            )

            company_data["deferred_revenue_journal_id"] = company_data.get(
                "deferred_revenue_journal_id"
            ) or next(
                (
                    xid
                    for xid, d in data["account.journal"].items()
                    if d["type"] == "general"
                ),
                None,
            )

            company_data["deferred_expense_account_id"] = company_data.get(
                "deferred_expense_account_id"
            ) or next(
                (
                    xid
                    for xid, d in data["account.account"].items()
                    if d["account_type"] == "asset_current"
                ),
                None,
            )

            company_data["deferred_revenue_account_id"] = company_data.get(
                "deferred_revenue_account_id"
            ) or next(
                (
                    xid
                    for xid, d in data["account.account"].items()
                    if d["account_type"] == "liability_current"
                ),
                None,
            )
            _debug.logic(
                "deferred_defaults_resolved",
                chart=chart_template,
                expense_journal=company_data.get("deferred_expense_journal_id"),
                revenue_journal=company_data.get("deferred_revenue_journal_id"),
                expense_account=company_data.get("deferred_expense_account_id"),
                revenue_account=company_data.get("deferred_revenue_account_id"),
            )

        return data

    @_debug.perf.timed
    def _post_load_data(self, template_code, company, template_data):
        _debug.lifecycle("_post_load_data", records=self)
        super()._post_load_data(template_code, company, template_data)

        self._install_sepa_modules(company)

    def _install_sepa_modules(self, companies) -> None:
        sepa_countries = self.env.ref("base.sepa_zone").country_ids
        in_sepa = any(company.country_id in sepa_countries for company in companies)
        _debug.logic("sepa_zone_checked", companies=companies, in_sepa=in_sepa)
        if not in_sepa:
            return
        sepa_modules = (
            self.env["ir.module.module"]
            .sudo()
            .search([("name", "in", SEPA_MODULES), ("state", "=", "uninstalled")])
        )
        if not sepa_modules:
            return
        immediate = bool(
            self.env.registry.ready
            and not modules.module.current_test
            and not self.env.context.get("install_demo")
        )
        _debug.logic(
            "sepa_module_install_mode",
            companies=companies,
            modules=sepa_modules,
            immediate=immediate,
        )
        if immediate:
            sepa_modules.button_immediate_install()
        else:
            sepa_modules.button_install()

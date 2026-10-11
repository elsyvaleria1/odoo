from odoo import models

from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template(model="account.journal")
    def _get_account_reports_journal(self, template_code) -> dict:
        return {
            "tax_returns": {
                "name": self.env._("Tax Returns"),
                "type": "general",
                "code": "TAX",
                "show_on_dashboard": False,
            },
        }

    @template(model="res.company")
    def _get_account_reports_res_company(self, chart_template) -> dict:
        company = self.env.company
        return {
            company.id: {
                "account_tax_return_journal_id": company.account_config_id.account_tax_return_journal_id.id
                or "tax_returns",
            },
        }

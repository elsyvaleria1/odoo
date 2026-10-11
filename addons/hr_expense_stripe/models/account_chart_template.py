from odoo import models

from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"
    _name = "account.chart.template"

    @template(model="account.journal")
    def _get_stripe_issuing_account_journal(self, template_code) -> dict:
        return {
            "stripe_issuing_journal": {
                "code": "STRPI",
                "name": self.env._("Stripe Issuing"),
                "type": "bank",
                "currency_id": self.env.company.stripe_currency_id.id,
                "bank_statements_source": "stripe_issuing",
                "sequence": 20,
            }
        }

    @template(model="res.company")
    def _prepare_stripe_issuing_company_data(self, template_code) -> dict:
        return {
            self.env.company.id: {
                "stripe_journal_id": "stripe_issuing_journal",
            }
        }

    def _post_load_data(self, template_code, company, template_data):
        res = super()._post_load_data(template_code, company, template_data)
        company._create_stripe_issuing_journal()
        if company.stripe_currency_id and not company.stripe_journal_id.currency_id:
            company.stripe_journal_id.currency_id = company.stripe_currency_id
        company._stripe_issuing_setup_mcc()
        return res

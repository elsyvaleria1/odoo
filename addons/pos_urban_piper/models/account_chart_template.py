from odoo import models

from odoo.addons.account.models.chart_template import template

URBANPIPER_FISCAL_POSITION = "pos_account_fiscal_position_urbanpiper"


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template(model="account.fiscal.position")
    def _get_pos_urban_piper_account_fiscal_position(self, template_code) -> dict:
        return {URBANPIPER_FISCAL_POSITION: {"name": "Urbanpiper"}}

    def _load_urbanpiper_fiscal_positions(self) -> None:
        for company in self.env["res.company"].search(
            [
                ("account_config_id.chart_template", "!=", False),
                ("parent_id", "=", False),
            ]
        ):
            ChartTemplate = self.with_company(company)
            xml_id = ChartTemplate.company_xmlid(URBANPIPER_FISCAL_POSITION)
            if self.env.ref(xml_id, raise_if_not_found=False):
                continue
            position = self.env["pos.config"]._urbanpiper_fiscal_position_of(company)
            if position:
                self.env["ir.model.data"]._update_xmlids(
                    [{"xml_id": xml_id, "record": position, "noupdate": True}]
                )
                continue
            ChartTemplate._load_data(
                {
                    "account.fiscal.position": ChartTemplate._get_pos_urban_piper_account_fiscal_position(
                        company.account_config_id.chart_template
                    )
                }
            )

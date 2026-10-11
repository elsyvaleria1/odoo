from typing import Literal

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResCurrency(models.Model):
    _inherit = "res.currency"

    @api.readonly
    @api.model
    def get_company_currency_for_spreadsheet(
        self, company_id=None
    ) -> dict | Literal[False]:
        company = (
            self.env["res.company"].browse(company_id)
            if company_id
            else self.env.company
        )
        if not company.exists():
            _debug.logic(
                "spreadsheet_company_currency_missing",
                reason="unknown_company",
                company_id=company_id,
            )
            return False
        currency = company.currency_id
        _debug.logic(
            "spreadsheet_company_currency_resolved", company=company, currency=currency
        )
        return {
            "code": currency.name,
            "symbol": currency.symbol,
            "decimalPlaces": currency.decimal_places,
            "position": currency.position,
        }

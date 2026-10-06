from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _prepare_purchase_order_vals(self, company_id, origins, values):
        _debug.pipeline("agreement_po_vals", rules=self, company=company_id)
        res = super()._prepare_purchase_order_vals(company_id, origins, values)
        values = values[0]
        res["partner_ref"] = values["supplier"].agreement_id.name
        res["agreement_id"] = values["supplier"].agreement_id.id
        if values["supplier"].agreement_id.currency_id:
            res["currency_id"] = values["supplier"].agreement_id.currency_id.id
        return res

    def _get_fallback_supplier(self, product_id, company_id):
        _debug.logic("agreement_fallback_supplier", rules=self, product=product_id)
        return product_id._prepare_sellers(False).filtered(
            lambda s: (
                not s.agreement_id and (not s.company_id or s.company_id == company_id)
            ),
        )[:1]

    def _get_domain_po(self, company_id, values, partner):
        _debug.logic("agreement_po_domain", rules=self, partner=partner)
        domain = super()._get_domain_po(company_id, values, partner)
        if "supplier" in values and values["supplier"].agreement_id:
            domain += (("agreement_id", "=", values["supplier"].agreement_id.id),)
        return domain

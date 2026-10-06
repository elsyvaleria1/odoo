from odoo.http import route
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale.controllers.portal import CustomerPortal

_debug = DebugLog(__name__)


class CustomerPortalExternalTax(CustomerPortal):
    @route()
    def portal_my_order(self, *args, **kwargs):
        response = super().portal_my_order(*args, **kwargs)
        if "sale_order" not in response.qcontext:
            return response

        # Update taxes before customers see their quotation. This also ensures that tax validation
        # works (e.g. customer has valid address, ...). Otherwise, errors will occur during quote
        # confirmation. Switch company so that property fields are read correctly.
        so = response.qcontext["sale_order"]
        _debug.pipeline("portal_order_taxes_refreshed", order=so)
        so.with_company(so.company_id)._get_and_set_external_taxes_on_eligible_records()

        return response

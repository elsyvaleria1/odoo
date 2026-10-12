from odoo.fields import Domain

from odoo.addons.portal.controllers import portal_thread


class PortalChatter(portal_thread.PortalChatter):
    def _get_domain_portal_message_fetch_extra(self, data) -> Domain:
        domain = super()._get_domain_portal_message_fetch_extra(data)
        if data.get("rating_value", False) is not False:
            try:
                rating_value = float(data["rating_value"])
            except TypeError, ValueError:
                return domain
            domain &= Domain("rating_value", "=", rating_value)
        return domain

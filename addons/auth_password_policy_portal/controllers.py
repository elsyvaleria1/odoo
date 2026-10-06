from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class CustomerPortalPasswordPolicy(CustomerPortal):
    def _prepare_portal_layout_values(self):
        d = super()._prepare_portal_layout_values()
        d["password_minimum_length"] = request.env.registry.settings.get(
            request.env, "auth_password_policy.minlength", False
        )
        return d

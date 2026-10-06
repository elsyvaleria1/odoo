import logging

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class Website(models.Model):
    _inherit = "website"

    @api.model
    def action_dashboard_redirect(self):
        _debug.lifecycle(
            "dashboard_redirect",
            user=self.env.user,
            salesman=self.env.user.has_group("sale.group_sale_salesman"),
        )
        if self.env.user.has_group("sale.group_sale_salesman"):
            return self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "website_sale_dashboard.sale_dashboard"
            )
        return super().action_dashboard_redirect()

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    intercompany_generate_sales_orders = fields.Boolean(string="Generate Sales order")
    intercompany_generate_purchase_orders = fields.Boolean(
        string="Generate Purchase Orders"
    )

    def _get_intercompany_uid_or_raise(self):
        """Return this company's intercompany user id, or raise.

        Shared by sale_order.py/purchase_order.py so both SO->PO and PO->SO
        generation report the same "no intercompany user configured" error
        instead of each hand-rolling its own message. Deliberately narrower
        than account_inter_company_rules's res.company._check_intercompany_config,
        which also requires a purchase journal — irrelevant to plain SO/PO
        generation and not something this method should pull in.
        """
        self.check_singleton()
        if not self.intercompany_user_id:
            _debug.logic("intercompany_user_missing", company=self)
            raise UserError(
                self.env._(
                    "Provide one user for intercompany relation for %(name)s",
                    name=self.name,
                )
            )
        return self.intercompany_user_id.id

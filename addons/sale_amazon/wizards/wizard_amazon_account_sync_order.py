import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class WizardAmazonAccountSyncOrder(models.TransientModel):
    _name = "wizard.amazon.account.sync.order"
    _description = "Amazon Recover Order Wizard"

    amazon_order_ref = fields.Char(
        string="Amazon Order Reference",
        required=True,
        help="The reference to the Amazon order to recover, in 3-7-7 format",
    )

    @api.constrains("amazon_order_ref")
    def _check_amazon_order_ref(self) -> None:
        for wizard in self:
            amazon_order_ref_pattern = re.compile(r"^\d{3}-\d{7}-\d{7}$")
            if not re.match(amazon_order_ref_pattern, wizard.amazon_order_ref):
                raise ValidationError(
                    self.env._("The Amazon order reference must be in 3-7-7 format.")
                )

    def action_recover_order(self):
        for wizard in self:
            account = self.env["amazon.account"].browse(self.env.context["active_id"])
            return account._sync_order_by_reference(wizard.amazon_order_ref)
        return None

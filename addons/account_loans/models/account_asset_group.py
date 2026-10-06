from odoo import fields, models

from .common import records_action


class AccountAssetGroup(models.Model):
    _inherit = "account.asset.group"

    linked_loan_ids = fields.One2many(
        comodel_name="account.loan",
        inverse_name="asset_group_id",
        string="Related Loans",
    )
    count_linked_loans = fields.Count(count_of="linked_loan_ids")

    def action_view_linked_loans(self):
        self.check_singleton()
        return records_action(self.name, self.linked_loan_ids)

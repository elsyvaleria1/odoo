from odoo import fields, models

from .common import records_action


class AccountDepreciationBoard(models.Model):
    _inherit = "account.depreciation.board"

    linked_loans_ids = fields.One2many(related="asset_group_id.linked_loan_ids")
    count_linked_loans = fields.Count(count_of="linked_loans_ids")

    def action_view_linked_loans(self):
        return records_action(self.env._("Linked loans"), self.linked_loans_ids)

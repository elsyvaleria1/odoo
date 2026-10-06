from odoo import fields, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    approval_request_ids = fields.One2many(
        comodel_name="approval.request",
        inverse_name="bank_statement_line_id",
        string="Claiming Approval Requests",
        help="Approval requests that claim this bank transaction. Used by the "
        "request's own picker to leave out transactions another live request "
        "already holds.",
    )

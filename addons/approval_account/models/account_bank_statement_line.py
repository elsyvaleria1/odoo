from typing import Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.fields import Domain


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

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        lines = super().create(vals_list)
        self.env["approval.request"]._claim_bank_statement_lines(lines.company_id)
        return lines

    def _get_domain_settled_elsewhere(self) -> Domain:
        return super()._get_domain_settled_elsewhere() | Domain(
            "approval_request_ids",
            "any",
            [("state", "not in", ("refused", "cancelled"))],
        )

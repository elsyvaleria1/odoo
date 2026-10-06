from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    automation_intercompany_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Intercompany Collection Journal",
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        check_company=True,
        help="Journal this company books a collection in when another company's "
        "bank received the money: the customer's receivable is settled "
        "against what the receiving company owes this one.",
    )

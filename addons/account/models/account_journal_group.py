from odoo import fields, models

from odoo.addons.base.models.mixin_catalog import name_uniq_index


class AccountJournalGroup(models.Model):
    _name = "account.journal.group"
    _description = "Account Journal Group"
    _order = "sequence"
    _check_company_auto = True
    _get_domain_company_compatible = models.get_domain_company_parent_of

    name = fields.Char(
        string="Ledger group",
        translate=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        help="Define which company can select the multi-ledger in report filters. If none is provided, available for all companies",
    )
    excluded_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        string="Excluded Journals",
        domain='company_id and [("company_id", "parent_of", company_id)] or []',
        context={"active_test": False},
    )
    sequence = fields.Integer(default=10)

    _name_src_uniq = name_uniq_index(
        "company_id",
        nulls_distinct=True,
        message="A Ledger group name must be unique per company.",
    )

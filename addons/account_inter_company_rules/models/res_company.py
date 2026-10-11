from typing import Self

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = "res.company"

    intercompany_generate_bills_refund = fields.Boolean(
        string="Generate Bills and Refunds"
    )
    intercompany_document_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Validated"),
        ],
        string="Automation",
        default="draft",
    )
    intercompany_purchase_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Purchase Journal",
        compute="_compute_intercompany_purchase_journal_id",
        store=True,
        readonly=False,
        domain='[("type", "=", "purchase"), ("company_id", "parent_of", id)]',
    )
    intercompany_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Create as",
        default=SUPERUSER_ID,
        domain=["|", ["active", "=", True], ["id", "=", SUPERUSER_ID]],
        help="Responsible user for creation of documents triggered by intercompany rules.",
    )

    @api.model
    def _find_company_from_partner(self, partner_id) -> Self:
        if not partner_id:
            return self.sudo().browse()
        return self._find_companies_from_partners(
            self.env["res.partner"].browse(partner_id)
        )[partner_id]

    @api.model
    def _find_companies_from_partners(self, partners) -> dict[int, Self]:
        if not partners:
            return {}
        companies = self.sudo().search([("partner_id", "parent_of", partners.ids)])
        none = companies.browse()
        by_partner = {}
        for partner in partners.with_env(companies.env).with_context(active_test=False):
            lineage = set()
            ancestor = partner
            while ancestor and ancestor.id not in lineage:
                lineage.add(ancestor.id)
                ancestor = ancestor.parent_id
            by_partner[partner.id] = next(
                (company for company in companies if company.partner_id.id in lineage),
                none,
            )
        return by_partner

    @api.depends("account_config_id.chart_template")
    def _compute_intercompany_purchase_journal_id(self) -> None:
        journals_by_company = dict(
            self.env["account.journal"]._read_group(
                domain=[("type", "=", "purchase")],
                groupby=["company_id"],
                aggregates=["id:recordset"],
            )
        )

        for company in self:
            if not company.intercompany_purchase_journal_id:
                company.intercompany_purchase_journal_id = journals_by_company.get(
                    company, [False]
                )[0]

    def _get_intercompany_purchase_journal(self):
        self.check_singleton()
        journal = self.intercompany_purchase_journal_id
        if journal and journal.company_id in self.parent_ids:
            return journal
        return (
            self.env["account.journal"]
            .sudo()
            .search([("type", "=", "purchase"), ("company_id", "=", self.id)], limit=1)
        )

    def _check_intercompany_config(self) -> None:
        self.check_singleton()
        if not self.intercompany_user_id:
            raise UserError(
                self.env._(
                    "No user is set for the inter-company relation of %(company)s."
                    " Set one under Settings > Inter-Company Transactions >"
                    " Create as.",
                    company=self.name,
                )
            )
        if not self._get_intercompany_purchase_journal():
            raise UserError(
                self.env._(
                    "No purchase journal is available for the inter-company"
                    " relation of %(company)s. Set one under Settings >"
                    " Inter-Company Transactions > Purchase Journal.",
                    company=self.name,
                )
            )

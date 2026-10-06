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
        return self.sudo().search([("partner_id", "parent_of", partner_id)], limit=1)

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
        """Return the journal the generated vendor bills must be booked in.

        ``intercompany_purchase_journal_id`` is computed from ``chart_template``,
        which the chart loader writes *before* it creates the chart's own journals,
        so the stored value is left empty on every company whose chart is loaded
        after this module is installed. Branch companies never own a purchase
        journal at all. Fall back to a live lookup rather than feeding ``False``
        to the generated bill.

        The stored value is only trusted when it actually belongs to this
        company or one of its ancestors (a branch may legitimately book onto
        its parent's journal) — a manually set, unrelated company's journal
        falls back to the live lookup instead of being returned unchecked.
        """
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
        """Validate what this company needs before documents are generated in it.

        Generation runs inside the *source* company's ``_post_entries``, so a
        setting missing here rolls back an unrelated, legitimate customer
        invoice. Fail with an actionable message naming the company and the
        setting, rather than with a raw ``NotNullViolation`` (no journal) or a
        bare ``AccessError`` (no user, because ``with_user(False)`` silently
        returns ``self``).
        """
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

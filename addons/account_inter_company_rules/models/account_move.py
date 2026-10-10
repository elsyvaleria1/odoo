from odoo import api, fields, models
from odoo.tools import clean_context

from odoo.addons.account.tools.display_types import NON_ACCOUNTABLE_DISPLAY_TYPES


class AccountMove(models.Model):
    _inherit = "account.move"

    auto_generated = fields.Boolean(
        string="Auto Generated Document",
        default=False,
        copy=False,
    )
    auto_invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Source Invoice",
        index="btree_not_null",
        copy=False,
        readonly=True,
    )

    def _post_entries(self):
        # OVERRIDE to generate cross invoice based on company rules.
        invoices_map = {}
        posted = super()._post_entries()
        candidates = posted.filtered(lambda move: move.is_sale_document())
        # Resetting a source invoice to draft and re-posting it must not produce
        # a second vendor bill: the first mirror is still there and nothing
        # links it back or cancels it.
        already_mirrored = (
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "in", candidates.ids)])
            .auto_invoice_id
        )
        for invoice in candidates - already_mirrored:
            company_sudo = (
                self.env["res.company"]
                .sudo()
                ._find_company_from_partner(invoice.partner_id.id)
            )
            if (
                company_sudo
                # invoicing a partner of your own company is not an
                # inter-company transaction: mirroring it books a phantom
                # liability against the company that issued the invoice.
                and company_sudo != invoice.company_id
                and company_sudo.intercompany_generate_bills_refund
                and not invoice.auto_generated
            ):
                invoices_map.setdefault(company_sudo, self.env["account.move"])
                invoices_map[company_sudo] += invoice
        for company_sudo, invoices in invoices_map.items():
            company_sudo._check_intercompany_config()
            # Drop every default_* the posting user happens to carry rather
            # than a hand-maintained deny list: anything left over is applied
            # to a document in another company. default_move_type is re-added
            # per record by _inter_company_create_invoices.
            context = clean_context(self.env.context)
            context["default_company_id"] = company_sudo.id
            invoices.with_user(company_sudo.intercompany_user_id.id).with_context(
                context
            ).with_company(company_sudo.id)._inter_company_create_invoices(company_sudo)
        return posted

    def _inter_company_create_invoices(self, company):
        """Create cross company invoices.
        :param company: the company the mirror documents are created in. The
                        caller is expected to have applied ``with_company``
                        already; taking it explicitly keeps that contract
                        visible instead of reading it back off ``env.company``.
        :return:        The newly created invoices.
        """

        # Prepare invoice values.
        invoices_vals = []
        inverse_types = {
            "out_invoice": "in_invoice",
            "out_refund": "in_refund",
        }
        for inv in self:
            invoice_vals = inv._inter_company_prepare_invoice_data(
                inverse_types[inv.move_type], company
            )
            invoice_vals["invoice_line_ids"] = []
            for line in inv.invoice_line_ids:
                invoice_vals["invoice_line_ids"].append(
                    (0, 0, line._inter_company_prepare_invoice_line_data(company))
                )

            inv_new = inv.with_context(default_move_type=invoice_vals["move_type"]).new(
                invoice_vals
            )
            for line in inv_new.invoice_line_ids.filtered(
                lambda l: l.display_type not in NON_ACCOUNTABLE_DISPLAY_TYPES
            ):
                # We need to adapt the taxes following the fiscal position, but we must keep the
                # price unit.
                price_unit = line.price_unit
                line.tax_ids = line._get_computed_taxes()
                line.price_unit = price_unit

            invoice_vals = inv_new._convert_to_write(inv_new._cache)
            invoice_vals.pop("line_ids", None)
            invoices_vals.append((inv, invoice_vals))

        # Create invoices.
        moves = self.create([vals for _origin, vals in invoices_vals])
        auto_post = company.intercompany_document_state == "posted"
        for (origin_invoice, _vals), move in zip(invoices_vals, moves, strict=True):
            move.message_post(
                body=self.env._(
                    "Automatically generated from %(origin)s of company %(company)s.",
                    origin=origin_invoice.name,
                    company=origin_invoice.company_id.name,
                )
            )
            if not auto_post:
                continue
            if move._get_held_for_posting_approval():
                move.message_post(
                    body=self.env._(
                        "Left in draft: posting it needs an approval, which an "
                        "automatic posting cannot ask for. Post it to ask for one."
                    )
                )
            else:
                move._post(soft=True)
        return moves

    def _inter_company_prepare_invoice_data(self, invoice_type, company):
        r"""Get values to create the invoice.
        /!\ Doesn't care about lines, see '_inter_company_prepare_invoice_line_data'.
        :param invoice_type: the move type of the invoice to create.
        :param company:      the company the invoice is created in.
        :return: Python dictionary of values.
        """
        self.check_singleton()
        # We need the fiscal position in the company we are creating the invoice
        # in, not the fiscal position of the current invoice (self.company_id).
        delivery_partner_id = self.company_id.partner_id.address_get(["delivery"])[
            "delivery"
        ]
        delivery_partner = self.env["res.partner"].browse(delivery_partner_id)
        fiscal_position = self.env["account.fiscal.position"]._get_fiscal_position(
            self.company_id.partner_id, delivery=delivery_partner, company=company
        )
        vals = {
            "move_type": invoice_type,
            "ref": self.name,
            "partner_id": self.company_id.partner_id.id,
            "currency_id": self.currency_id.id,
            "auto_generated": True,
            "auto_invoice_id": self.id,
            "company_id": company.id,
            "invoice_date": self.invoice_date,
            "invoice_date_due": self.invoice_date_due,
            "payment_reference": self.payment_reference,
            "invoice_origin": self.env._(
                "%(company)s Invoice: %(entry)s",
                company=self.company_id.name,
                entry=self.name,
            ),
            "fiscal_position_id": fiscal_position.id,
            "invoice_payment_term_id": self.invoice_payment_term_id.id
            if self.invoice_payment_term_id
            and not self.invoice_payment_term_id.company_id
            else False,
        }
        # Leave the key out entirely when the company has no purchase journal at
        # all: a False here reaches the NOT NULL column verbatim and aborts the
        # source company's own post with a raw NotNullViolation.
        journal = company._get_intercompany_purchase_journal()
        if journal:
            vals["journal_id"] = journal.id
        return vals


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def _inter_company_is_out_of_reach(self, records, company):
        """Whether ``company`` cannot see these company-owned records.

        Both ``product.product`` and ``account.analytic.account`` are guarded by
        a ``['|', ('company_id', '=', False), ('company_id', 'parent_of',
        company_ids)]`` guard, so a record owned by ``company`` itself or
        by any of its ancestors is perfectly readable there. Owning *a* company
        is therefore not the same as being out of reach, which is what the two
        call sites used to test.
        """
        return records.filtered(
            lambda record: (
                record.company_id and record.company_id not in company.parent_ids
            )
        )

    def _inter_company_prepare_invoice_line_data(self, company):
        """Get values to create the invoice line.
        :param company: the company the invoice line is created in.
        :return: Python dictionary of values.
        """
        self.check_singleton()

        vals = {
            "display_type": self.display_type,
            "sequence": self.sequence,
            "name": self.name,
            "quantity": self.quantity,
            "discount": self.discount,
            "price_unit": self.price_unit,
        }
        if self._inter_company_is_out_of_reach(self.product_id, company):
            vals["name"] = self.product_id.name
        else:
            vals.update(
                {
                    "product_id": self.product_id.id,
                    "product_uom_id": self.product_uom_id.id,
                }
            )

        company_a_partner = self.company_id.partner_id
        company_b_default_distribution = self.env[
            "account.analytic.distribution.model"
        ]._get_distribution(
            {
                "product_id": self.product_id.id,
                "product_categ_id": self.product_id.categ_id.id,
                "partner_id": company_a_partner.id,
                "partner_tag_id": company_a_partner.tag_ids.ids,
                "account_prefix": self.account_id.code,
                "company_id": company.id,
            }
        )

        analytic_distribution = {}
        if self.analytic_distribution:
            unreachable_account_ids = set(
                self._inter_company_is_out_of_reach(
                    self.distribution_analytic_account_ids, company
                ).ids
            )

            analytic_distribution = {
                key: val
                for key, val in self.analytic_distribution.items()
                if not any(
                    int(account_id) in unreachable_account_ids
                    for account_id in key.split(",")
                )
            }

        # Combine Company B's default distribution model with the line's own
        # distribution from Company A (filtered above to accounts valid in
        # Company B); on overlapping keys the line's distribution wins.
        if company_b_default_distribution or analytic_distribution:
            vals["analytic_distribution"] = dict(
                company_b_default_distribution, **analytic_distribution
            )

        return vals

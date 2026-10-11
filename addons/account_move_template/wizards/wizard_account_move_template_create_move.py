import math
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

PURCHASE_MOVE_TYPES = ("in_invoice", "in_refund")
SALE_MOVE_TYPES = ("out_invoice", "out_refund")


class WizardAccountMoveTemplateCreateMove(models.TransientModel):
    _name = "wizard.account.move.template.create.move"
    _description = "Wizard to generate move from template"

    ref = fields.Char()
    amount = fields.Float()
    customize_lines = fields.Boolean(
        default=False,
        help="Enable to manually edit journal entry lines before creation",
    )
    date = fields.Date(
        default=fields.Date.context_today,
        required=True,
    )
    template_id = fields.Many2one(
        comodel_name="account.move.template",
        required=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        domain="['|', ('parent_id', '=', False), ('is_company', '=', True)]",
    )
    third_party_id = fields.Many2one(
        comodel_name="res.partner",
        help="The party a document is made out to in place of the partner, "
        "such as the generic public for a customer who takes no fiscal "
        "invoice. Informational by default: partner_id stays on the "
        "generated document (task t22217). Only a template that ticks "
        "'Issue to the Third Party' is issued to this one instead.",
    )
    multicompany_id = fields.Many2one(
        comodel_name="res.company",
        help="Target company to use when creating the journal entry, if different.",
    )
    line_ids = fields.One2many(
        comodel_name="wizard.account.move.template.create.move.line",
        inverse_name="wizard_id",
    )
    move_type = fields.Selection(related="template_id.move_type")
    is_payment = fields.Boolean(
        related="template_id.is_payment",
        readonly=True,
    )
    payment_type = fields.Selection(
        related="template_id.payment_type",
        readonly=True,
    )
    partner_type = fields.Selection(
        related="template_id.partner_type",
        readonly=True,
    )

    @api.onchange("customize_lines", "template_id", "multicompany_id")
    def _onchange_customize_lines(self) -> None:
        if self.customize_lines and self.template_id:
            self.load_lines()
        else:
            self.line_ids = [Command.clear()]

    @api.constrains("amount")
    def _check_amount_is_not_negative(self) -> None:
        if invalid := self.filtered(
            lambda wizard: not (math.isfinite(wizard.amount) and wizard.amount >= 0),
        ):
            raise ValidationError(
                self.env._(
                    "Template '%(template)s' cannot run for a negative amount "
                    "(%(amount)s). Use a credit note or an outbound payment "
                    "template for money going the other way.",
                    template=invalid[0].template_id.name,
                    amount=invalid[0].amount,
                ),
            )

    def _resolve_company(self) -> models.Model:
        return self.multicompany_id or self.template_id.company_id or self.env.company

    def _get_move_partner(self) -> models.Model:
        self.check_singleton()
        if self.template_id.use_third_party and self.third_party_id:
            return self.third_party_id

        return self.partner_id

    def _get_template_line_accounts(
        self, tmpl_lines: models.Model, company: models.Model
    ) -> dict[str, models.Model]:
        codes = set(tmpl_lines.mapped("account_code"))
        accounts = self.env["account.move.template.line"]._resolve_codes_in_company(
            codes,
            company,
        )
        if missing := sorted(codes - accounts.keys()):
            raise UserError(
                self.env._(
                    "No account found with code '%(code)s' for company '%(company)s'",
                    code="', '".join(missing),
                    company=company.name,
                )
            )
        return accounts

    def load_lines(self) -> None:
        self.check_singleton()
        self.line_ids = [Command.clear()] + [
            Command.create(vals) for vals in self._prepare_wizard_lines()
        ]

    def _prepare_wizard_lines(self) -> list[dict[str, Any]]:
        tmpl_lines = self.template_id.line_ids
        product_lines = tmpl_lines.filtered(lambda line: line.display_type == "product")
        company = self._resolve_company()
        accounts = self._get_template_line_accounts(product_lines, company)
        shares = iter(self._distribute_amount(len(product_lines)))

        vals_list = []
        for tmpl_line in tmpl_lines:
            if tmpl_line.display_type == "product":
                vals_list.extend(
                    self._prepare_wizard_line(
                        tmpl_line,
                        accounts[tmpl_line.account_code],
                        next(shares),
                    ),
                )
            else:
                vals_list.append(self._prepare_display_line(tmpl_line))

        _debug.logic(
            "lines_prepared",
            template=self.template_id,
            company=company,
            amount=self.amount,
            template_lines=len(tmpl_lines),
            wizard_lines=len(vals_list),
        )
        return vals_list

    def _prepare_display_line(self, tmpl_line: models.Model) -> dict[str, Any]:
        return {
            "template_line_id": tmpl_line.id,
            "display_type": tmpl_line.display_type,
            "name": tmpl_line.name,
            "sequence": tmpl_line.sequence,
        }

    def _distribute_amount(self, count: int) -> list[float]:
        if count <= 0:
            return []
        if not self.amount or count == 1:
            return [self.amount] * count

        currency = self._resolve_company().currency_id
        share = currency.round(self.amount / count)
        return [share] * (count - 1) + [
            currency.round(self.amount - share * (count - 1))
        ]

    def _get_journal(self, company: models.Model) -> models.Model:
        code = self.template_id.journal_code
        journal = (
            self.env["account.journal"]
            .with_company(company)
            .search(
                [
                    ("code", "=", code),
                    ("company_id", "=", company.id),
                    ("active", "=", True),
                    *(
                        [("type", "in", journal_types)]
                        if (journal_types := self.template_id._get_journal_types())
                        else []
                    ),
                ],
                limit=1,
            )
        )
        if not journal:
            raise UserError(
                self.env._(
                    "No active journal with code '%(code)s' in %(company)s "
                    "can hold what template '%(template)s' creates.",
                    code=code,
                    company=company.name,
                    template=self.template_id.name,
                ),
            )
        return journal

    def create_payment(self) -> models.Model:
        self.check_singleton()
        if not self.amount:
            raise UserError(
                self.env._(
                    "Template '%(template)s' creates a payment, so this run "
                    "needs an amount.",
                    template=self.template_id.name,
                ),
            )

        company = self._resolve_company()
        journal = self._get_journal(company)
        return (
            self.env["account.payment"]
            .with_company(company)
            .create(self._prepare_payment_vals(journal))
        )

    def _prepare_payment_vals(self, journal: models.Model) -> dict[str, Any]:
        return {
            "date": self.date,
            "payment_type": self.payment_type,
            "partner_type": self.partner_type,
            "partner_id": self._get_move_partner().id,
            "journal_id": journal.id,
            "amount": self.amount,
            "memo": self.ref,
        }

    def action_create_move(self) -> dict[str, Any]:
        self.check_singleton()
        record = self.create_move()
        return {
            "type": "ir.actions.act_window",
            "name": record._description,
            "res_model": record._name,
            "view_mode": "form",
            "res_id": record.id,
        }

    def create_move(self) -> models.Model:
        self.check_singleton()
        if self.is_payment:
            return self.create_payment()

        if self.move_type == "entry" and self.amount:
            raise UserError(
                self.env._(
                    "Template '%(template)s' creates a journal entry, which "
                    "books the balances stored on its lines, so it cannot "
                    "honour the amount %(amount)s this run carries. Clear "
                    "the amount, or use a template with an invoice move "
                    "type.",
                    template=self.template_id.name,
                    amount=self.amount,
                ),
            )

        company = self._resolve_company()
        journal = self._get_journal(company)
        if not self.customize_lines:
            self.load_lines()

        if not self.line_ids.filtered(lambda line: line.display_type == "product"):
            raise UserError(
                self.env._(
                    "Template '%(template)s' produced no accounting line, so "
                    "there is nothing to create. Check that it has at least "
                    "one product line.",
                    template=self.template_id.name,
                ),
            )

        move_vals = self._prepare_move_vals(journal)
        move_vals["line_ids"] = [
            Command.create(self._prepare_move_line_vals(line)) for line in self.line_ids
        ]
        return self.env["account.move"].with_company(company).create(move_vals)

    def _prepare_move_line_vals(self, line: models.Model) -> dict[str, Any]:
        return self.env["account.move"]._prepare_template_move_line_vals(
            line, self.move_type, self._get_move_partner(),
        )

    def _prepare_move_vals(self, journal: models.Model) -> dict[str, Any]:
        return {
            "journal_id": journal.id,
            "move_type": self.move_type,
            "partner_id": self._get_move_partner().id,
            "invoice_payment_term_id": (
                self.template_id.invoice_payment_term_id.id
                if self.move_type != "entry"
                else False
            ),
            "date": self.date,
            "invoice_date": self.date if self.move_type != "entry" else False,
            "ref": self.ref,
            "company_id": journal.company_id.id,
        }

    def _get_template_line_product(
        self, tmpl_line: models.Model, amount: float
    ) -> models.Model:
        return tmpl_line.product_id

    def _product_price_unit(self, product: models.Model) -> float:
        if not product:
            return 0.0

        product = product.with_company(self._resolve_company())
        if self.move_type in PURCHASE_MOVE_TYPES:
            return product.standard_price
        if self.move_type in SALE_MOVE_TYPES:
            return product.lst_price
        return 0.0

    def _get_product_taxes(self, product: models.Model) -> models.Model:
        company = self._resolve_company()
        if self.move_type in PURCHASE_MOVE_TYPES:
            return product.supplier_taxes_id._filter_taxes_by_company(company)
        if self.move_type in SALE_MOVE_TYPES:
            return product.taxes_id._filter_taxes_by_company(company)
        return self.env["account.tax"]

    def _prepare_wizard_line(
        self, tmpl_line: models.Model, account: models.Model, amount: float
    ) -> list[dict[str, Any]]:
        product = self._get_template_line_product(tmpl_line, amount)
        known_price = tmpl_line.price_unit or self._product_price_unit(product)
        price_unit = known_price or 1.0
        taxes = tmpl_line.tax_ids or self._get_product_taxes(product)

        product_uom = tmpl_line.product_uom_id
        if not product_uom or product != tmpl_line.product_id:
            product_uom = product.uom_id

        base_vals = {
            "template_line_id": tmpl_line.id,
            "display_type": "product",
            "name": product.name if product else tmpl_line.name,
            "sequence": tmpl_line.sequence,
            "partner_id": tmpl_line.partner_id.id,
            "account_id": account.id,
            "analytic_distribution": tmpl_line.analytic_distribution or None,
            "product_id": product.id,
            "product_uom_id": product_uom.id,
            "discount": tmpl_line.discount,
            "balance": tmpl_line.balance,
            "tax_ids": [Command.set(taxes.ids)],
        }

        if not amount:
            return [
                {**base_vals, "quantity": tmpl_line.quantity, "price_unit": price_unit}
            ]
        if tmpl_line.distribution_method == "split" and known_price > 0:
            return self._split_line_vals(base_vals, known_price, amount)
        return [{**base_vals, "quantity": 1, "price_unit": amount}]

    def _split_line_vals(
        self,
        base_vals: dict[str, Any],
        price_unit: float,
        amount: float,
    ) -> list[dict[str, Any]]:
        currency = self._resolve_company().currency_id
        amount = currency.round(amount)
        full_units = math.floor(amount / price_unit)
        if currency.is_zero(amount - (full_units + 1) * price_unit):
            full_units += 1
        remainder = currency.round(amount - full_units * price_unit)

        _debug.logic(
            "amount_split",
            amount=amount,
            price_unit=price_unit,
            units=full_units,
            remainder=remainder,
        )
        if not full_units:
            return [{**base_vals, "quantity": 1, "price_unit": amount}]

        vals_list = [{**base_vals, "quantity": full_units, "price_unit": price_unit}]
        if not currency.is_zero(remainder):
            vals_list.append(
                {
                    **base_vals,
                    "quantity": 1,
                    "price_unit": remainder,
                    "sequence": base_vals["sequence"] + 1,
                }
            )
        return vals_list

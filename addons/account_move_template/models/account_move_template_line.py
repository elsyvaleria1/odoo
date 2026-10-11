from collections.abc import Iterable

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError


class AccountMoveTemplateLine(models.Model):
    _name = "account.move.template.line"
    _description = "Journal Item Template"
    _inherit = ["mixin.analytic"]
    _order = "sequence, id"
    _check_company_auto = True

    account_code = fields.Char(
        string="Accounts Prefix",
        help="When creating a new journal item an account having this prefix will be looked for. "
        "Required for product lines; ignored for section/note lines.",
    )
    name = fields.Char(string="Label")
    sequence = fields.Integer(
        compute="_compute_sequence",
        precompute=True,
        store=True,
        readonly=False,
    )
    quantity = fields.Float(
        digits="Product Unit",
        default=1.0,
    )
    price_unit = fields.Float(
        string="Unit Price",
        digits="Product Price",
    )
    discount = fields.Float(
        string="Discount (%)",
        digits="Discount",
    )
    balance = fields.Float(digits="Product Price")
    distribution_method = fields.Selection(
        selection=[
            ("collapse", "Collapse (one line, full amount)"),
            ("split", "Split (decompose into units of price_unit)"),
        ],
        default="collapse",
        required=True,
        help="How the wizard distributes the runtime amount across move lines.\n"
        "- Collapse: produce a single line with quantity=1 and price=amount. "
        "Use for discount, fee, single-item credit-note templates where "
        "price_unit on the template line is just a placeholder.\n"
        "- Split: decompose the amount into N units priced at price_unit each, "
        "with an adjustment line for the fractional remainder. Use for bills "
        "expressed as 'N units at price_unit'.",
    )
    display_type = fields.Selection(
        selection=[
            ("product", "Product"),
            ("line_section", "Section"),
            ("line_note", "Note"),
        ],
        default="product",
        required=True,
        help="Section and note lines carry no accounting value: they are "
        "written to the generated document as display lines, in sequence with "
        "the product lines around them.",
    )
    template_id = fields.Many2one(
        comodel_name="account.move.template",
        string="Move Template",
        index=True,
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        domain=["|", ("parent_id", "=", False), ("is_company", "=", True)],
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        compute="_compute_account_id",
        inverse="_inverse_account_id",
        store=False,
        readonly=False,
        domain=[("active", "=", True), ("account_type", "!=", "off_balance")],
        help="The account `account_code` resolves to. Pick one to fill the prefix.",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        check_company=True,
    )
    tax_ids = fields.Many2many(
        comodel_name="account.tax",
        string="Taxes",
        check_company=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="template_id.company_id",
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit of Measure",
        compute="_compute_product_uom_id",
        store=True,
        readonly=False,
    )

    _unique_template_sequence = models.UniqueIndex(
        "(template_id, sequence) NULLS NOT DISTINCT",
        "The sequence of the line must be unique per template!",
    )

    @api.model
    def _resolve_codes_in_company(
        self, codes: Iterable[str], company: models.Model
    ) -> dict[str, models.Model]:
        codes = {code for code in codes if code}
        if not codes:
            return {}

        domain = [("active", "=", True)]
        if company:
            domain.append(("company_ids", "in", company.ids))

        accounts = (
            self.env["account.account"]
            .with_company(company or self.env.company)
            .search(
                domain
                + ["|"] * (len(codes) - 1)
                + [("code", "=ilike", code + "%") for code in sorted(codes)],
            )
        )

        resolved: dict[str, models.Model] = {}
        for code in codes:
            prefix = code.upper()
            exact = accounts.filtered(lambda account, code=code: account.code == code)
            match = exact[:1] or accounts.filtered(
                lambda account, prefix=prefix: (
                    (account.code or "").upper().startswith(prefix)
                ),
            )[:1]
            if match:
                resolved[code] = match
        return resolved

    @api.depends("template_id")
    def _compute_sequence(self) -> None:
        highest: dict[int, int] = {}
        for line in self:
            if line.sequence:
                continue

            template_id = line.template_id.id
            if template_id not in highest:
                highest[template_id] = max(
                    line.template_id.line_ids.mapped("sequence") or [0],
                )
            highest[template_id] += 10
            line.sequence = highest[template_id]

    def _resolve_account_codes(self) -> dict[tuple[int, str], models.Model]:
        codes_by_company: dict[int, set[str]] = {}
        for line in self.filtered("account_code"):
            codes_by_company.setdefault(line.company_id.id, set()).add(
                line.account_code,
            )

        companies = self.env["res.company"]
        resolved: dict[tuple[int, str], models.Model] = {}
        for company_id, codes in codes_by_company.items():
            matches = self._resolve_codes_in_company(
                codes,
                companies.browse(company_id),
            )
            for code, account in matches.items():
                resolved[(company_id, code)] = account
        return resolved

    @api.depends_context("allowed_company_ids")
    @api.depends("account_code", "company_id")
    def _compute_account_id(self) -> None:
        resolved = self._resolve_account_codes()
        for line in self:
            line.account_id = resolved.get(
                (line.company_id.id, line.account_code),
                self.env["account.account"],
            )

    def _inverse_account_id(self) -> None:
        for line in self.filtered("account_id"):
            line.account_code = line.account_id.code

    @api.constrains("account_code", "company_id", "display_type", "template_id")
    def _check_account_code_exists(self) -> None:
        product_lines = self.filtered(lambda line: line.display_type == "product")
        if not product_lines:
            return

        for line in product_lines:
            if not line.account_code:
                raise ValidationError(
                    self.env._(
                        "Template line '%(line)s' must have an account code.",
                        line=line.name or f"Line {line.sequence}",
                    ),
                )

        resolved = product_lines._resolve_account_codes()
        for line in product_lines:
            if (line.company_id.id, line.account_code) in resolved:
                continue

            raise ValidationError(
                self.env._(
                    "No active account found matching code '%(code)s' "
                    "for line '%(line)s'. Please verify the account code.",
                    code=line.account_code,
                    line=line.name or f"Line {line.sequence}",
                ),
            )

    def write(self, vals: ValuesType) -> bool:
        templates = self.template_id
        result = super().write(vals)
        if {"display_type", "template_id"} & vals.keys():
            (templates | self.template_id)._check_template_keeps_its_lines()
        return result

    def unlink(self) -> bool:
        templates = self.template_id
        result = super().unlink()
        templates.exists()._check_template_keeps_its_lines()
        return result

    @api.depends("product_id")
    def _compute_product_uom_id(self) -> None:
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id
            else:
                line.product_uom_id = False

from itertools import starmap, zip_longest

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

from odoo.addons.trade.tools import TradeDirection

_debug = DebugLog(__name__)


class MixinOrderTemplate(models.AbstractModel):
    _name = "mixin.order.template"
    _description = "Order Template"
    _order = "sequence, id"
    _direction: TradeDirection | None = None

    active = fields.Boolean(
        default=True,
        help="If unchecked, it will allow you to hide the template without "
        "removing it.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    name = fields.Char(
        string="Template",
        required=True,
    )
    note = fields.Html(
        string="Terms and conditions",
        translate=True,
    )
    sequence = fields.Integer(default=10)
    number_of_days = fields.Integer(
        string="Validity",
        help="Number of days an order made from this template stays valid.",
    )
    line_ids = fields.One2many(
        comodel_name="mixin.order.template.line",
        inverse_name="template_id",
        string="Lines",
        copy=True,
    )

    @api.constrains("company_id", "line_ids")
    def _check_company_id(self) -> None:
        for template in self:
            restricted_products = template.line_ids.product_id.filtered("company_id")
            if not restricted_products:
                continue

            if not template.company_id:
                _debug.logic(
                    "template_company_rejected",
                    template=template,
                    reason="shared_template_with_company_products",
                    products=restricted_products,
                )
                raise ValidationError(
                    self.env._(
                        "Your template cannot contain products from specific companies if it's shared"
                        " between companies. Please restrict the template access, or remove those"
                        " products."
                    )
                )

            authorized_products = restricted_products.filtered_domain(
                self.env["product.product"]._check_company_domain(template.company_id)
            )
            if unauthorized_products := restricted_products - authorized_products:
                unaccessible_companies = unauthorized_products.company_id
                _debug.logic(
                    "template_company_rejected",
                    template=template,
                    reason="products_from_other_companies",
                    products=unauthorized_products,
                )
                if len(unaccessible_companies) > 1:
                    raise ValidationError(
                        self.env._(
                            "Your template belongs to company %(template_company)s but contains"
                            " products from other companies (%(product_company)s) that are not"
                            " accessible to %(template_company)s.\nPlease change the company of your"
                            " template or remove the products from other companies.",
                            product_company=", ".join(
                                unaccessible_companies.mapped("display_name")
                            ),
                            template_company=template.company_id.display_name,
                        )
                    )

                raise ValidationError(
                    self.env._(
                        "Your template belongs to company %(template_company)s but contains"
                        " products from company (%(product_company)s) that are not"
                        " accessible to %(template_company)s.\nPlease change the company of your"
                        " template or remove the products from other companies.",
                        product_company=unaccessible_companies.display_name,
                        template_company=template.company_id.display_name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _debug.lifecycle("create", templates=records, rows=len(vals_list))
        for record, vals in zip(records, vals_list, strict=True):
            if "line_ids" in vals:
                record._update_product_translations()
        return records

    def write(self, vals):
        _debug.lifecycle("write", templates=self, fields=list(vals))
        result = super().write(vals)
        if "line_ids" in vals:
            self._update_product_translations()
        return result

    def _update_product_translations(self) -> None:
        for code, _lang_name in self.env["res.lang"].get_installed():
            for line in self.line_ids:
                if line.name == line._get_product_description():
                    line.with_context(lang=code).name = line.with_context(
                        lang=code
                    )._get_product_description()


class MixinOrderTemplateLine(models.AbstractModel):
    _name = "mixin.order.template.line"
    _description = "Order Template Line"
    _order = "template_id, sequence, id"

    _accountable_product_id_required = models.Constraint(
        "CHECK(display_type IS NOT NULL OR (product_id IS NOT NULL AND product_uom_id IS NOT NULL))",
        "Missing required product and UoM on accountable template line.",
    )
    _non_accountable_fields_null = models.Constraint(
        "CHECK(display_type IS NULL OR (product_id IS NULL AND product_qty = 0 AND product_uom_id IS NULL))",
        "Forbidden product, quantity and UoM on non-accountable template line",
    )

    template_id = fields.Many2one(
        comodel_name="mixin.order.template",
        index=True,
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        default=10,
        help="Gives the sequence order when displaying the template lines.",
    )
    company_id = fields.Many2one(
        related="template_id.company_id",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        domain=lambda self: self._domain_product_id(),
        check_company=True,
    )
    name = fields.Text(
        string="Description",
        translate=True,
    )
    allowed_uom_ids = fields.Many2many(
        comodel_name="uom.uom",
        compute="_compute_allowed_uom_ids",
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
        compute="_compute_product_uom_id",
        precompute=True,
        store=True,
        readonly=False,
        domain="[('id', 'in', allowed_uom_ids)]",
    )
    product_qty = fields.Float(
        string="Quantity",
        digits="Product Unit",
        default=1,
        required=True,
    )
    display_type = fields.Selection(
        selection=[
            ("line_section", "Section"),
            ("line_subsection", "Subsection"),
            ("line_note", "Note"),
        ],
        default=False,
    )
    parent_id = fields.Many2one(
        comodel_name="mixin.order.template.line",
        string="Parent Section Line",
        compute="_compute_parent_id",
    )

    @api.depends("product_id", "product_id.uom_id", "product_id.uom_ids")
    def _compute_allowed_uom_ids(self):
        for line in self:
            line.allowed_uom_ids = line.product_id.uom_id | line.product_id.uom_ids

    @api.depends("product_id")
    def _compute_product_uom_id(self):
        for line in self:
            line.product_uom_id = line.product_id.uom_id

    @api.depends(
        "display_type",
        "sequence",
        "template_id.line_ids.display_type",
        "template_id.line_ids.sequence",
    )
    def _compute_parent_id(self) -> None:
        requested = set(self)
        for template, lines in self.grouped("template_id").items():
            if not template:
                lines.parent_id = False
                continue
            last_section = False
            last_sub = False
            for line in template.line_ids.sorted("sequence"):
                if line.display_type == "line_section":
                    last_section = line
                    if line in requested:
                        line.parent_id = False
                    last_sub = False
                elif line.display_type == "line_subsection":
                    if line in requested:
                        line.parent_id = last_section
                    last_sub = line
                elif line in requested:
                    line.parent_id = last_sub or last_section

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get(
                "display_type", self.default_get(["display_type"])["display_type"]
            ):
                vals.update(product_id=False, product_qty=0, product_uom_id=False)
        return super().create(vals_list)

    def write(self, vals):
        if "display_type" in vals and self.filtered(
            lambda line: line.display_type != vals.get("display_type")
        ):
            raise UserError(
                self.env._(
                    "You cannot change the type of a template line. Instead you "
                    "should delete the current line and create a new line of the "
                    "proper type."
                )
            )
        return super().write(vals)

    @api.model
    def _domain_product_id(self):
        direction = self.env[self._fields["template_id"].comodel_name]._direction
        if direction is None:
            return [("type", "!=", "combo")]
        return [(direction.product_ok_field, "=", True), ("type", "!=", "combo")]

    def _get_product_description(self):
        self.check_singleton()
        return self.product_id.display_name

    def _prepare_order_line_values(self):
        self.check_singleton()
        vals = {
            "display_type": self.display_type,
            "product_id": self.product_id.id,
            "product_qty": self.product_qty,
            "product_uom_id": self.product_uom_id.id,
            "sequence": self.sequence,
        }
        if self.name:
            vals["name"] = self.name
        return vals


class MixinOrderTemplated(models.AbstractModel):
    _name = "mixin.order.templated"
    _description = "Order Made From a Template"

    template_id = fields.Many2one(
        comodel_name="mixin.order.template",
        domain="[('company_id', 'in', [False, company_id])]",
        check_company=True,
    )

    @api.onchange("template_id")
    def _onchange_template_id(self) -> None:
        if not self.template_id:
            _debug.logic("template_lines_skipped", reason="no_template")
            return

        template = self.template_id.with_context(lang=self.partner_id.lang)
        lines = [Command.clear()]
        lines += [
            Command.create(line._prepare_order_line_values())
            for line in template.line_ids
        ]
        if len(lines) >= 2:
            lines[1][2]["sequence"] = -99

        _debug.pipeline(
            "order_lines_from_template",
            order=self._origin,
            template=self.template_id,
            lines=len(lines) - 1,
        )
        self.line_ids = lines

    @api.onchange("partner_id")
    def _onchange_partner_id_reapply_template(self) -> None:
        if self._origin or not self.template_id:
            return

        def untouched(line, template_line):
            return (
                line
                and template_line
                and line.product_qty == template_line.product_qty
                and all(
                    line[fname] == template_line[fname]
                    for fname in ("product_id", "product_uom_id", "display_type")
                )
            )

        if all(
            starmap(untouched, zip_longest(self.line_ids, self.template_id.line_ids))
        ):
            _debug.logic(
                "template_lines_reapplied",
                order=self._origin,
                template=self.template_id,
                reason="lines_untouched",
            )
            self._onchange_template_id()

    def _get_template_line_name(self, line):
        template_line = next(
            (
                template_line
                for template_line in self.template_id.line_ids
                if template_line.product_id == line.product_id and template_line.name
            ),
            None,
        )
        if template_line is None:
            return None
        return template_line.with_context(lang=self.partner_id.lang).name

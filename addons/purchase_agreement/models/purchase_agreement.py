from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict

from odoo.addons.trade.tools import PURCHASE


class PurchaseAgreement(models.Model):
    _name = "purchase.agreement"
    _inherit = ["mixin.agreement"]
    _description = "Purchase Agreement"
    _direction = PURCHASE

    user_id = fields.Many2one(string="Purchase Representative")
    order_count = fields.Count(
        count_of="order_ids",
        string="Number of Orders",
    )
    order_ids = fields.One2many(
        comodel_name="purchase.order",
        inverse_name="agreement_id",
        string="Purchase Orders",
    )
    line_ids = fields.One2many(
        comodel_name="purchase.agreement.line",
        inverse_name="agreement_id",
        string="Products to Purchase",
        copy=True,
    )
    break_ids = fields.One2many(
        comodel_name="purchase.agreement.line.break",
        inverse_name="agreement_id",
        string="Quantity Breaks",
        copy=False,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        related="line_ids.product_id",
        string="Product",
    )
    previous_agreement_id = fields.Many2one(comodel_name="purchase.agreement")

    def _get_sequence_code(self, agreement_type):
        return {
            "blanket_order": "purchase.agreement.blanket.order",
        }[agreement_type]

    def _get_partner_currency(self, partner):
        return partner.property_purchase_currency_id


class PurchaseAgreementLine(models.Model):
    _name = "purchase.agreement.line"
    _inherit = ["mixin.agreement.line"]
    _description = "Purchase Agreement Line"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    order_line_ids = fields.One2many(comodel_name="purchase.order.line")
    break_ids = fields.One2many(comodel_name="purchase.agreement.line.break")
    currency_id = fields.Many2one(related="agreement_id.currency_id")
    product_id = fields.Many2one(domain=[("purchase_ok", "=", True)])
    product_description_variants = fields.Char(string="Description")
    agreement_id = fields.Many2one(
        comodel_name="purchase.agreement",
        string="Purchase Agreement",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="agreement_id.company_id",
        string="Company",
        readonly=True,
    )
    supplier_info_ids = fields.One2many(
        comodel_name="product.supplierinfo",
        inverse_name="agreement_line_id",
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line, vals in zip(lines, vals_list, strict=True):
            if (
                line.agreement_id.agreement_type == "blanket_order"
                and line.agreement_id.state not in ["draft", "done", "cancel"]
                and line.product_id
            ):
                if line.price_unit <= 0.0:
                    raise UserError(
                        self.env._(
                            "You cannot have a negative or unit price of 0 for an already confirmed blanket order."
                        )
                    )
                supplier_infos = self.env["product.supplierinfo"].search(  # noqa: E8507 -- one lookup per confirmed line, on its own product and vendor
                    [
                        ("product_id", "=", vals.get("product_id")),
                        (
                            "partner_id",
                            "=",
                            line.agreement_id.partner_id.commercial_partner_id.id,
                        ),
                    ]
                )
                if not any(s.agreement_id for s in supplier_infos):
                    line._create_supplier_info()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "price_unit" not in vals:
            return res
        if vals["price_unit"] <= 0.0 and any(
            agreement.agreement_type == "blanket_order"
            and agreement.state not in ["draft", "done", "cancel"]
            for agreement in self.mapped("agreement_id")
        ):
            raise UserError(
                self.env._(
                    "You cannot have a negative or unit price of 0 for an already confirmed blanket order."
                )
            )
        self._sync_supplier_info()
        return res

    def unlink(self):
        to_unlink = self.filtered(
            lambda r: r.agreement_id.state not in ["draft", "done", "cancel"]
        )
        to_unlink._projected_vendor_prices().unlink()
        return super().unlink()

    def _on_agreement_confirmed(self) -> None:
        for line in self:
            line._create_supplier_info()

    def _on_agreement_closed(self) -> None:
        self._projected_vendor_prices().unlink()

    def _create_supplier_info(self) -> None:
        self.check_singleton()
        agreement = self.agreement_id
        if (
            agreement.agreement_type == "blanket_order"
            and agreement.partner_id
            and self.product_id
        ):
            self.env["product.supplierinfo"].with_privilege(
                "purchase_agreement.privilege_project_vendor_prices",
                reason="a blanket order line's prices",
            ).create(
                [
                    self._prepare_supplier_info_values(0.0, self.price_unit),
                    *(
                        self._prepare_supplier_info_values(
                            rule.min_qty, rule.price_unit
                        )
                        for rule in self.break_ids
                    ),
                ]
            )

    def _prepare_supplier_info_values(self, min_qty, price) -> dict:
        agreement = self.agreement_id
        return {
            "partner_id": agreement.partner_id.commercial_partner_id.id,
            "product_id": self.product_id.id,
            "product_uom_id": self.product_uom_id.id,
            "product_tmpl_id": self.product_id.product_tmpl_id.id,
            "min_qty": min_qty,
            "price": price,
            "currency_id": agreement.currency_id.id,
            "date_start": agreement.date_start,
            "date_end": agreement.date_end,
            "agreement_line_id": self.id,
        }

    def _sync_supplier_info(self) -> None:
        for line in self.filtered(lambda line: line.agreement_id.state == "confirmed"):
            line._projected_vendor_prices().unlink()
            line._create_supplier_info()

    def _projected_vendor_prices(self):
        return self.supplier_info_ids.with_privilege(
            "purchase_agreement.privilege_project_vendor_prices",
            reason="a blanket order line's prices",
        )

    def _add_description_variants(self, name):
        if not self or not self.product_description_variants:
            return name
        return name + "\n" + self.product_description_variants

    def _prepare_order_line_values(self, product_qty, tax_ids):
        values = super()._prepare_order_line_values(product_qty, tax_ids)
        date_commitment = fields.Datetime.now()
        if self.agreement_id.date_start:
            date_commitment = max(
                date_commitment,
                fields.Datetime.to_datetime(self.agreement_id.date_start),
            )
        values["date_commitment"] = date_commitment
        return values


class PurchaseAgreementLineBreak(models.Model):
    _name = "purchase.agreement.line.break"
    _inherit = ["mixin.agreement.line.break"]
    _description = "Purchase Agreement Quantity Break"
    _check_company_auto = True

    agreement_id = fields.Many2one(comodel_name="purchase.agreement")
    line_id = fields.Many2one(comodel_name="purchase.agreement.line")

    @api.model_create_multi
    def create(self, vals_list):
        breaks = super().create(vals_list)
        breaks.line_id._sync_supplier_info()
        return breaks

    def write(self, vals):
        lines = self.line_id
        result = super().write(vals)
        (lines | self.line_id)._sync_supplier_info()
        return result

    def unlink(self):
        lines = self.line_id
        result = super().unlink()
        lines.exists()._sync_supplier_info()
        return result

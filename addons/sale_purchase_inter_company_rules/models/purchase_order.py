from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    auto_generated = fields.Boolean(
        string="Auto Generated Purchase Order",
        copy=False,
    )
    auto_sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Source Sales Order",
        index=True,
        copy=False,
        readonly=True,
    )

    def _action_confirm(self):
        res = super()._action_confirm()
        for order in self:
            company_rec = self.env["res.company"]._find_company_from_partner(
                order.partner_id.id
            )
            if (
                company_rec
                and company_rec.intercompany_generate_sales_orders
                and not order.auto_generated
                and not self.env["sale.order"]
                .sudo()
                .search_count(
                    [
                        ("auto_purchase_order_id", "=", order.id),
                        ("state", "!=", "cancel"),
                    ],
                    limit=1,
                )
            ):
                order.with_user(company_rec.intercompany_user_id).with_context(
                    default_company_id=company_rec.id
                ).with_company(company_rec).inter_company_create_sale_order(company_rec)
        return res

    def inter_company_create_sale_order(self, company) -> None:
        intercompany_uid = company._get_intercompany_uid_or_raise()
        if not self.env["sale.order"].with_user(intercompany_uid).has_access("create"):
            _debug.logic(
                "intercompany_refused",
                purchase_orders=self,
                company=company,
                reason="no_create_access",
            )
            raise UserError(
                self.env._(
                    "Inter company user of company %(name)s doesn't have enough access rights",
                    name=company.name,
                )
            )

        for rec in self:
            company_partner = rec.company_id.partner_id.with_user(intercompany_uid)
            if (
                company_partner.property_product_pricelist
                and rec.currency_id.id
                != company_partner.property_product_pricelist.currency_id.id
            ):
                _debug.logic(
                    "intercompany_refused",
                    purchase_order=rec,
                    company=company,
                    reason="currency_mismatch",
                )
                raise UserError(
                    self.env._(
                        "You cannot create SO from PO because sale price list currency is different "
                        "than purchase price list currency.\n"
                        "The currency of the SO is obtained from the pricelist of the company partner.\n\n"
                        "(SO currency: %(so_currency)s, Pricelist: %(pricelist)s, Partner: %(partner)s (ID: %(id)s))",
                        so_currency=rec.currency_id.name,
                        pricelist=company_partner.property_product_pricelist.display_name,
                        partner=company_partner.display_name,
                        id=company_partner.id,
                    )
                )

            _debug.pipeline(
                "intercompany_sale_order_prepared", purchase_order=rec, company=company
            )
            sale_order_data = rec.sudo()._prepare_sale_order_data(
                rec.name, company_partner, company, rec.dest_address_id.id or False
            )

            for line in rec.line_ids.sudo():
                sale_order_data["line_ids"] += [
                    Command.create(rec._prepare_sale_order_line_data(line, company))
                ]
            sale_order = (
                self.env["sale.order"]
                .with_context(
                    allowed_company_ids=company.ids,
                    in_rental_app=False,
                )
                .with_user(intercompany_uid)
                .create(sale_order_data)
            )
            msg = self.env._(
                "Automatically generated from %(origin)s of company %(company)s.",
                origin=self.name,
                company=rec.company_id.name,
            )
            sale_order.message_post(body=msg)

            if not rec.partner_ref:
                rec.partner_ref = sale_order.name

            if company.intercompany_document_state == "posted":
                sale_order.with_user(intercompany_uid).action_confirm()

    def _prepare_sale_order_data(self, name, partner, company, direct_delivery_address):
        self.check_singleton()
        partner_addr = partner.sudo().address_get(["invoice", "delivery", "contact"])

        return {
            "name": self.env["ir.sequence"].sudo().next_by_code("sale.order") or "/",
            "company_id": company.id,
            "client_order_ref": name,
            "partner_id": partner.id,
            "pricelist_id": partner.property_product_pricelist.id,
            "partner_invoice_id": partner_addr["invoice"],
            "date_order": self.date_order,
            "fiscal_position_id": self.env["account.fiscal.position"]
            ._get_fiscal_position(partner)
            .id,
            "payment_term_id": partner.property_payment_term_id.id,
            "user_id": False,
            "auto_generated": True,
            "auto_purchase_order_id": self.id,
            "partner_shipping_id": direct_delivery_address or partner_addr["delivery"],
            "date_commitment": self.date_commitment,
            "line_ids": [],
        }

    @api.model
    def _prepare_sale_order_line_data(self, line, company):
        price = line.price_unit or 0.0
        quantity = line.product_uom_qty
        price = (
            line.product_id
            and line.product_uom_id._get_price_in_unit(price, line.product_id.uom_id)
        ) or price
        return {
            "name": line.name,
            "product_qty": quantity,
            "product_id": (line.product_id and line.product_id.id) or False,
            "product_uom_id": (line.product_id and line.product_id.uom_id.id)
            or line.product_uom_id.id,
            "price_unit": price,
            "discount": line.discount or 0.0,
            "company_id": company.id,
            "display_type": line.display_type,
        }

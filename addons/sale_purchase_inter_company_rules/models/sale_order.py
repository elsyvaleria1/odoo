from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    auto_generated = fields.Boolean(
        string="Auto Generated Sales Order",
        copy=False,
    )
    auto_purchase_order_id = fields.Many2one(
        comodel_name="purchase.order",
        string="Source Purchase Order",
        index=True,
        copy=False,
        readonly=True,
    )

    def _action_confirm(self):
        """Generate inter company purchase order based on conditions"""
        res = super()._action_confirm()
        for order in self:
            if (
                not order.company_id
            ):  # if company_id not found, return to normal behavior
                continue
            # if company allow to create a Purchase Order from Sales Order, then do it!
            company = self.env["res.company"]._find_company_from_partner(
                order.partner_id.id
            )
            if (
                company
                and company.intercompany_generate_purchase_orders
                and not order.auto_generated
                and not self.env["purchase.order"]
                .sudo()
                .search_count(
                    [
                        ("auto_sale_order_id", "=", order.id),
                        ("state", "!=", "cancel"),
                    ],
                    limit=1,
                )
            ):
                order.with_user(company.intercompany_user_id).with_context(
                    default_company_id=company.id
                ).with_company(company).inter_company_create_purchase_order(company)
        return res

    def inter_company_create_purchase_order(self, company) -> None:
        """Create a Purchase Order from the current SO (self)
        Note : In this method, reading the current SO is done as sudo, and the creation of the derived
        PO as intercompany_user, minimizing the access right required for the trigger user
        :param company : the company of the created PO
        :rtype company : res.company record
        """
        for rec in self:
            if not company or not rec.company_id.partner_id:
                continue

            # find user for creating and validating SO/PO from company
            intercompany_uid = company._get_intercompany_uid_or_raise()
            # check intercompany user access rights
            if (
                not self.env["purchase.order"]
                .with_user(intercompany_uid)
                .has_access("create")
            ):
                _debug.logic(
                    "intercompany_refused",
                    order=rec,
                    company=company,
                    reason="no_create_access",
                )
                raise UserError(
                    self.env._(
                        "Inter company user of company %s doesn't have enough access rights",
                        company.name,
                    )
                )

            company_partner = rec.company_id.partner_id.with_user(intercompany_uid)
            # check purchase currency should be same with SO/PO document
            if (
                company_partner.property_purchase_currency_id
                and rec.currency_id.id
                != company_partner.property_purchase_currency_id.id
            ):
                _debug.logic(
                    "intercompany_refused",
                    order=rec,
                    company=company,
                    reason="currency_mismatch",
                )
                raise UserError(
                    self.env._(
                        "You cannot create PO from SO because purchase currency is "
                        "different than sale currency.\n"
                        "The currency of the PO is obtained from the currency of the SO.\n\n"
                        "(SO currency: %(so_currency)s, Purchase currency: %(purchase_currency)s, "
                        "Partner: %(partner)s (ID: %(id)s))",
                        so_currency=rec.currency_id.name,
                        purchase_currency=company_partner.property_purchase_currency_id.display_name,
                        partner=company_partner.display_name,
                        id=company_partner.id,
                    )
                )

            # create the PO and generate its lines from the SO
            # read it as sudo, because inter-compagny user can not have the access right on SO
            po_vals = rec.sudo()._prepare_purchase_order_data(company, company_partner)
            for line in rec.line_ids.sudo():
                po_vals["line_ids"] += [
                    (
                        0,
                        0,
                        rec._prepare_purchase_order_line_data(
                            line, rec.date_order, company
                        ),
                    )
                ]
            purchase_order = self.env["purchase.order"].create(po_vals)
            msg = self.env._(
                "Automatically generated from %(origin)s of company %(company)s.",
                origin=self.name,
                company=rec.company_id.name,
            )
            purchase_order.message_post(body=msg)

            # write customer reference field on SO
            if not rec.client_order_ref:
                rec.client_order_ref = purchase_order.name

            # auto-validate the purchase order if needed
            if company.intercompany_document_state == "posted":
                purchase_order.with_user(intercompany_uid).action_confirm()

    def _prepare_purchase_order_data(self, company, company_partner):
        """Generate purchase order values, from the SO (self)
        :param company_partner : the partner representing the company of the SO
        :rtype company_partner : res.partner record
        :param company : the company in which the PO line will be created
        :rtype company : res.company record
        """
        self.check_singleton()

        return {
            "name": self.env["ir.sequence"].sudo().next_by_code("purchase.order"),
            "origin": self.name,
            "partner_id": company_partner.id,
            "date_order": self.date_order,
            "company_id": company.id,
            "fiscal_position_id": self.env["account.fiscal.position"]
            ._get_fiscal_position(company_partner)
            .id,
            "payment_term_id": company_partner.property_supplier_payment_term_id.id,
            "auto_generated": True,
            "auto_sale_order_id": self.id,
            "partner_ref": self.name,
            "currency_id": self.currency_id.id,
            "line_ids": [],
        }

    @api.model
    def _prepare_purchase_order_line_data(self, so_line, date_order, company) -> dict:
        """Generate purchase order line values, from the SO line
        :param so_line : origin SO line
        :rtype so_line : sale.order.line record
        :param date_order : the date of the orgin SO
        :param company : the company in which the PO line will be created
        :rtype company : res.company record
        """
        # discount is copied as its own field below, not folded into price_unit
        price = so_line.price_unit or 0.0
        quantity = so_line.product_uom_qty  # already in the product's reference UoM
        price = (
            so_line.product_id
            and so_line.product_uom_id._get_price_in_unit(
                price, so_line.product_id.uom_id
            )
        ) or price
        return {
            "name": so_line.name,
            "product_qty": quantity,
            "product_id": (so_line.product_id and so_line.product_id.id) or False,
            "product_uom_id": (so_line.product_id and so_line.product_id.uom_id.id)
            or so_line.product_uom_id.id,
            "price_unit": price or 0.0,
            "discount": so_line.discount or 0.0,
            "company_id": company.id,
            "date_commitment": so_line.order_id.date_commitment
            or so_line.order_id.date_planned
            or date_order,
            "display_type": so_line.display_type,
        }

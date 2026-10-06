from odoo import api, fields, models


class WizardPurchaseOrderInviteVendor(models.TransientModel):
    _name = "wizard.purchase.order.invite.vendor"
    _inherit = ["mixin.tender.invite"]
    _description = "Invite vendors to a tender"

    origin_order_id = fields.Many2one(comodel_name="purchase.order")
    tender_id = fields.Many2one(comodel_name="purchase.tender")
    partner_ids = fields.Many2many(
        string="Vendors",
        help="The vendors to invite: each receives a request for quotation.",
    )
    purchase_warn_msg = fields.Text(
        string="Warning Messages",
        compute="_compute_purchase_warn_msg",
        groups="purchase.group_warning_purchase",
    )

    @api.depends("partner_ids", "copy_products")
    def _compute_purchase_warn_msg(self) -> None:
        self.purchase_warn_msg = ""
        if not self.env.user.has_group("purchase.group_warning_purchase"):
            return
        for partner in self.partner_ids:
            if not partner.purchase_warn_msg:
                partner = partner.parent_id
            if partner and partner.purchase_warn_msg:
                self.purchase_warn_msg = self.env._(
                    "Warning for %(partner)s:\n%(warning_message)s\n",
                    partner=partner.name,
                    warning_message=partner.purchase_warn_msg,
                )
            if self.copy_products and self.origin_order_id.line_ids:
                for line in self.origin_order_id.line_ids:
                    if line.product_id.purchase_line_warn_msg:
                        self.purchase_warn_msg += self.env._(
                            "Warning for %(product)s:\n%(warning_message)s\n",
                            product=line.product_id.name,
                            warning_message=line.product_id.purchase_line_warn_msg,
                        )

    def _on_offers_created(self, offers) -> None:
        offers.line_ids._compute_tax_ids()

    def _prepare_offer_values(self):
        values = super()._prepare_offer_values()
        origin = self.origin_order_id
        for vals, partner in zip(values, self.partner_ids, strict=True):
            vals.update(
                {
                    "dest_address_id": origin.dest_address_id.id,
                    "currency_id": partner.property_purchase_currency_id.id
                    or self.env.company.currency_id.id,
                    "payment_term_id": partner.property_supplier_payment_term_id.id,
                }
            )
        return values

    def _prepare_offer_line_values(self, line, partner):
        values = super()._prepare_offer_line_values(line, partner)
        if not line.display_type and not self._has_vendor_description(
            partner, line.product_id
        ):
            values["name"] = line.name
        return values

    def _has_vendor_description(self, partner, product) -> bool:
        return bool(
            self.env["product.supplierinfo"].search_count(
                [
                    ("product_tmpl_id", "=", product.product_tmpl_id.id),
                    ("partner_id", "=", partner.id),
                    "|",
                    ("product_code", "!=", False),
                    ("product_name", "!=", False),
                ],
                limit=1,
            )
        )

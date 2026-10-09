from odoo import api, models
from odoo.fields import Domain


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._activate_or_create_pricelists()
        return companies

    def write(self, vals):
        if not vals.get("currency_id"):
            return super().write(vals)

        previous_currency = {company: company.currency_id for company in self}
        enabled_pricelists = self.env.user.has_group("product.group_product_pricelist")
        res = super(
            ResCompany, self.with_context(disable_company_pricelist_creation=True)
        ).write(vals)

        self._realign_default_pricelist_currency(previous_currency)

        if not enabled_pricelists and self.env.user.has_group(
            "product.group_product_pricelist"
        ):
            self._activate_or_create_pricelists()

        return res

    @api.model
    def _realign_default_pricelist_currency(self, previous_currency) -> None:
        domains = [
            Domain("company_id", "=", company.id)
            & Domain("currency_id", "=", currency.id)
            for company, currency in previous_currency.items()
            if currency and currency != company.currency_id
        ]
        if not domains:
            return
        candidates = (
            self.env["product.pricelist"]
            .sudo()
            .with_context(active_test=False)
            .search(Domain.OR(domains))
        )
        with_rules = {
            pricelist
            for (pricelist,) in self.env["product.pricelist.item"]
            .sudo()
            ._read_group([("pricelist_id", "in", candidates.ids)], ["pricelist_id"])
        }
        for pricelist in candidates:
            if pricelist not in with_rules:
                pricelist.currency_id = pricelist.company_id.currency_id

    def _activate_or_create_pricelists(self) -> None:
        if self.env.context.get("disable_company_pricelist_creation"):
            return

        if self.env.user.has_group("product.group_product_pricelist"):
            companies = self or self.env["res.company"].search([])
            ProductPricelist = self.env["product.pricelist"].sudo()
            default_pricelists_sudo = (
                ProductPricelist.with_context(active_test=False)
                .search([("item_ids", "=", False), ("company_id", "in", companies.ids)])
                .filtered(lambda pl: pl.currency_id == pl.company_id.currency_id)
            )
            default_pricelists_sudo.action_unarchive()
            companies_without_pricelist = companies.filtered(
                lambda c: c.id not in default_pricelists_sudo.company_id.ids
            )
            ProductPricelist.create(
                [
                    company._prepare_default_pricelist_vals()
                    for company in companies_without_pricelist
                ]
            )

    def _prepare_default_pricelist_vals(self):
        self.check_singleton()
        return {
            "name": self.env._("Default"),
            "currency_id": self.currency_id.id,
            "company_id": self.id,
            "sequence": 10,
        }

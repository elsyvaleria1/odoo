from odoo import fields, models
from odoo.fields import Domain


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    def _domain_item_ids(self):
        # Subscription pricings shouldn't appear in the main tab
        return Domain.AND([super()._domain_item_ids(), [("plan_id", "=", False)]])

    def _domain_subscription_item_ids(self):
        return Domain.AND(
            [self._get_domain_item_ids_base(), [("plan_id", "!=", False)]]
        )

    subscription_item_ids = fields.One2many(
        comodel_name="product.pricelist.item",
        inverse_name="pricelist_id",
        string="Recurring Pricing",
        copy=True,
        domain=lambda self: self._domain_subscription_item_ids(),
    )

    def _get_applicable_rules(self, products, date, *, plan_id=None, **kwargs):
        if not self:
            return self.env["product.pricelist.item"]

        self.check_singleton()

        recurring_rules = self.env["product.pricelist.item"]
        if plan_id:
            # Prepend the recurring rules if a plan is given, as they are expected to take priority
            # over the standard rules.
            recurring_rules = (
                self.env["product.pricelist.item"]
                .with_context(active_test=False)
                .search(
                    self._get_domain_applicable_rules(
                        products=products, date=date, plan_id=plan_id, **kwargs
                    ),
                    order=self.env[
                        "product.pricelist.item"
                    ]._get_recurring_rules_order(),
                )
                .with_context(self.env.context)
            )

        # Do not give plan_id to super call
        return recurring_rules | super()._get_applicable_rules(products, date, **kwargs)

    def _get_domain_applicable_rules(
        self, *args, plan_id=None, any_plan=False, **kwargs
    ):
        # Filter out subscription-rules targeting other products
        base_domain = super()._get_domain_applicable_rules(
            *args, plan_id=plan_id, **kwargs
        )

        if plan_id:
            # Only search recurring rules when a plan is given
            return Domain.AND([base_domain, [("plan_id", "=", plan_id)]])

        if any_plan:
            # Specific use-case (website_sale_subscription), fetch all the recurring rules applying
            # to a given product.
            return Domain.AND(
                [
                    base_domain,
                    [("plan_id", "!=", False)],
                ]
            )

        # Do not return recurring rules if no plan was given
        return Domain.AND([base_domain, [("plan_id", "=", False)]])

from odoo import fields, models
from odoo.tools import frozendict

from odoo.addons.sale_subscription.models.sale_order import SUBSCRIPTION_STATES


class SaleSubscriptionReport(models.Model):
    _name = "sale.subscription.report"
    _inherit = ["sale.report"]
    _description = "Subscription Analysis"
    _auto = False
    _depends = frozendict(
        {
            "product.product": ["product_tmpl_id", "volume", "weight"],
            "product.template": ["categ_id", "recurring_invoice", "uom_id"],
            "res.partner": [
                "commercial_partner_id",
                "country_id",
                "primary_industry_id",
                "state_id",
                "zip",
            ],
            "sale.order": [
                "campaign_id",
                "client_order_ref",
                "close_reason_id",
                "company_id",
                "currency_rate",
                "date_order",
                "end_date",
                "first_contract_date",
                "invoice_state",
                "is_subscription",
                "medium_id",
                "name",
                "next_invoice_date",
                "origin_order_id",
                "partner_id",
                "plan_id",
                "pricelist_id",
                "recurring_total",
                "template_id",
                "sent",
                "source_id",
                "state",
                "subscription_state",
                "team_id",
                "user_id",
            ],
            "sale.order.line": [
                "amount_taxexc_invoiced",
                "amount_taxexc_to_invoice",
                "discount",
                "display_type",
                "invoice_state",
                "is_downpayment",
                "order_id",
                "price_subtotal",
                "price_total",
                "price_unit",
                "product_id",
                "product_qty",
                "product_uom_id",
                "qty_invoiced",
                "qty_to_invoice",
                "qty_transferred",
            ],
            "sale.subscription.plan": ["repeat_interval", "repeat_unit"],
            "uom.uom": ["factor"],
        }
    )
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
            "owner": models.Anchor("user_id", shared=True),
        }
    )

    client_order_ref = fields.Char(
        string="Customer Reference",
        readonly=False,
    )
    first_contract_date = fields.Date(
        string="First contract date",
        readonly=True,
    )
    end_date = fields.Date(readonly=True)
    recurring_monthly = fields.Monetary(
        string="Monthly Recurring",
        readonly=True,
    )
    recurring_yearly = fields.Monetary(
        string="Yearly Recurring",
        readonly=True,
    )
    recurring_total = fields.Monetary(
        string="Recurring Revenue",
        readonly=True,
    )
    is_subscription = fields.Boolean(readonly=True)
    template_id = fields.Many2one(
        comodel_name="sale.order.template",
        string="Subscription Template",
        readonly=True,
    )
    country_id = fields.Many2one(
        comodel_name="res.country",
        string="Country",
        readonly=True,
    )
    commercial_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer Company",
        readonly=True,
    )
    industry_id = fields.Many2one(
        comodel_name="res.partner.industry",
        string="Industry",
        readonly=True,
    )
    close_reason_id = fields.Many2one(
        comodel_name="sale.order.close.reason",
        readonly=True,
    )
    margin = fields.Float()
    subscription_state = fields.Selection(
        selection=SUBSCRIPTION_STATES,
        readonly=True,
    )
    next_invoice_date = fields.Date(readonly=True)
    plan_id = fields.Many2one(
        comodel_name="sale.subscription.plan",
        readonly=True,
    )
    origin_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="First contract",
        readonly=True,
    )

    def _get_fields_select(self):
        res = super()._get_fields_select()
        res["is_subscription"] = "o.is_subscription"
        res["subscription_state"] = "o.subscription_state"
        res["end_date"] = "o.end_date"
        res["first_contract_date"] = "o.first_contract_date"
        res["template_id"] = "o.template_id"
        res["close_reason_id"] = "o.close_reason_id"
        res["next_invoice_date"] = "o.next_invoice_date"
        res["plan_id"] = "o.plan_id"
        res["origin_order_id"] = "o.origin_order_id"
        res["client_order_ref"] = "o.client_order_ref"
        res["margin"] = "0"
        res["recurring_monthly"] = f"""sum(l.price_subtotal)
            / CASE
                WHEN ssp.repeat_unit = 'week' THEN 7.0 / 30.437
                WHEN ssp.repeat_unit = 'month' THEN 1
                WHEN ssp.repeat_unit = 'year' THEN 12
                ELSE 1
             END
            / ssp.repeat_interval
            / {self._case_value_or_one("o.currency_rate")}
            * {self._case_value_or_one("account_currency_table.rate")}
        """
        res["recurring_yearly"] = f"""sum(l.price_subtotal)
            / CASE
                WHEN ssp.repeat_unit = 'week' THEN 7.0 / 30.437
                WHEN ssp.repeat_unit = 'month' THEN 1
                WHEN ssp.repeat_unit = 'year' THEN 12
                ELSE 1
             END
            / ssp.repeat_interval
            * 12
            / {self._case_value_or_one("o.currency_rate")}
            * {self._case_value_or_one("account_currency_table.rate")}
        """
        res["recurring_total"] = f"""
                o.recurring_total
                / {self._case_value_or_one("o.currency_rate")}
                * {self._case_value_or_one("account_currency_table.rate")}
        """
        return res

    def _get_from_tables(self) -> list:
        return [
            *super()._get_from_tables(),
            ("sale_subscription_plan", "ssp", "LEFT JOIN", "ssp.id = o.plan_id"),
        ]

    def _get_where_conditions(self) -> list:
        return [*super()._get_where_conditions(), "o.subscription_state IS NOT NULL"]

    def _get_fields_group_by(self) -> list:
        return [
            *super()._get_fields_group_by(),
            "o.subscription_state",
            "o.end_date",
            "o.template_id",
            "partner.primary_industry_id",
            "o.close_reason_id",
            "o.state",
            "o.next_invoice_date",
            "o.plan_id",
            "o.origin_order_id",
            "o.first_contract_date",
            "o.client_order_ref",
            "ssp.repeat_unit",
            "ssp.repeat_interval",
        ]

    def action_view_subscription_order(self):
        self.check_singleton()
        if self.order_reference._name == "sale.order":
            action = self.order_reference._get_associated_so_action()
            action["views"] = [
                (
                    self.env.ref(
                        "sale_subscription.sale_subscription_primary_form_view"
                    ).id,
                    "form",
                )
            ]
            action["res_id"] = self.order_reference.id
            return action
        return {
            "res_model": self._name,
            "type": "ir.actions.act_window",
            "views": [[False, "form"]],
            "res_id": self.id,
        }

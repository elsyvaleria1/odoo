from odoo import fields, models
from odoo.tools import SQL, frozendict

from odoo.addons.sale import const
from odoo.addons.sale_subscription.models.sale_order import (
    SUBSCRIPTION_PROGRESS_STATE,
    SUBSCRIPTION_STATES,
)


class SaleOrderLogReport(models.Model):
    _name = "sale.order.log.report"
    _description = "Sales Log Analysis Report"
    _order = "id desc"
    _auto = False
    _depends = frozendict(
        {
            "res.currency.rate": ["company_id", "currency_id", "name", "rate"],
            "res.partner": [
                "commercial_partner_id",
                "country_id",
                "primary_industry_id",
            ],
            "sale.order": [
                "campaign_id",
                "client_order_ref",
                "close_reason_id",
                "company_id",
                "currency_id",
                "end_date",
                "first_contract_date",
                "is_subscription",
                "partner_id",
                "plan_id",
                "pricelist_id",
                "template_id",
                "state",
                "team_id",
                "user_id",
            ],
            "sale.order.log": [
                "amount_signed",
                "date_effective",
                "event_date",
                "event_type",
                "order_id",
                "origin_order_id",
                "recurring_monthly",
                "subscription_state",
            ],
        }
    )
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Salesperson",
        readonly=True,
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        string="Sales Team",
        readonly=True,
    )
    client_order_ref = fields.Char(
        string="Customer Reference",
        readonly=True,
    )
    event_type = fields.Selection(
        selection=[
            ("0_creation", "New"),
            ("1_expansion", "Expansion"),
            ("15_contraction", "Contraction"),
            ("2_churn", "Churn"),
            ("3_transfer", "Transfer"),
        ],
        string="Type of event",
        readonly=True,
    )
    event_date = fields.Date(readonly=True)
    date_effective = fields.Date(
        readonly=True,
        help="Date the MRR change was first billed.",
    )
    contract_number = fields.Integer(
        string="Active Subscriptions Change",
        readonly=True,
    )
    pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        readonly=True,
    )
    amount_signed = fields.Monetary(
        string="MRR Change",
        currency_field="log_currency_id",
        readonly=True,
    )
    mrr_change_normalized = fields.Monetary(
        string="MRR Change (normalized)",
        readonly=True,
    )
    arr_change_normalized = fields.Monetary(
        string="ARR Change (normalized)",
        readonly=True,
    )
    recurring_monthly = fields.Monetary(
        string="Monthly Recurring Revenue",
        currency_field="log_currency_id",
        readonly=True,
    )
    recurring_yearly = fields.Monetary(
        string="Annual Recurring Revenue",
        currency_field="log_currency_id",
        readonly=True,
    )
    template_id = fields.Many2one(
        comodel_name="sale.order.template",
        string="Subscription Template",
        readonly=True,
    )
    plan_id = fields.Many2one(
        comodel_name="sale.subscription.plan",
        readonly=True,
    )
    country_id = fields.Many2one(
        comodel_name="res.country",
        string="Customer Country",
        readonly=True,
    )
    industry_id = fields.Many2one(
        comodel_name="res.partner.industry",
        string="Customer Industry",
        readonly=True,
    )
    commercial_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer Entity",
        readonly=True,
    )
    subscription_state = fields.Selection(
        selection=SUBSCRIPTION_STATES,
        readonly=True,
    )
    state = fields.Selection(
        selection=const.ORDER_STATE,
        string="Status",
        readonly=True,
    )
    campaign_id = fields.Many2one(
        comodel_name="utm.campaign",
        readonly=True,
    )
    origin_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="First Order",
        readonly=True,
    )
    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sale Order",
        readonly=True,
    )
    first_contract_date = fields.Date(readonly=True)
    end_date = fields.Date(readonly=True)
    close_reason_id = fields.Many2one(
        comodel_name="sale.order.close.reason",
        readonly=True,
    )
    currency_id = fields.Many2one(comodel_name="res.currency")
    log_currency_id = fields.Many2one(comodel_name="res.currency")

    def _with(self) -> SQL:
        return SQL(
            """
            rate_query AS (
                SELECT rc.id AS currency_id,
                       COALESCE(company_rates.rate, 1) AS rate
                  FROM res_currency rc
                  LEFT JOIN (%s) AS company_rates
                         ON company_rates.currency_id = rc.id
            )
            """,
            self.env["res.currency"]._select_companies_rates(
                company_ids=self.env.company.ids, date=SQL("CURRENT_DATE")
            ),
        )

    def _select(self):
        return f"""
            log.id AS id,
            so.client_order_ref AS client_order_ref,
            log.order_id AS order_id,
            log.event_type AS event_type,
            log.event_date AS event_date,
            log.date_effective as date_effective,
            so.user_id AS user_id,
            so.team_id AS team_id,
            so.partner_id AS partner_id,
            partner.country_id AS country_id,
            partner.primary_industry_id AS industry_id,
            so.template_id AS template_id,
            so.plan_id AS plan_id,
            so.company_id,
            partner.commercial_partner_id AS commercial_partner_id,
            log.subscription_state AS subscription_state,
            so.state AS state,
            so.pricelist_id AS pricelist_id,
            log.origin_order_id AS origin_order_id,
            log.amount_signed AS amount_signed,
            log.recurring_monthly AS recurring_monthly,
            log.recurring_monthly * 12 AS recurring_yearly,
            log.amount_signed * r2.rate/r1.rate AS mrr_change_normalized,
            log.amount_signed * 12 * r2.rate/r1.rate AS arr_change_normalized,
            r1.rate AS currency_rate,
            r2.rate AS user_rate,
            so.currency_id AS log_currency_id,
            {self.env.company.currency_id.id} AS currency_id,
            so.company_id AS log_cmp,
            CASE
                WHEN event_type = '0_creation' THEN 1
                WHEN event_type = '2_churn' THEN -1
                ELSE 0
            END as contract_number,
            so.campaign_id AS campaign_id,
            so.first_contract_date AS first_contract_date,
            so.end_date AS end_date,
            so.close_reason_id AS close_reason_id
        """

    def _from(self):
        currency_id = self.env.company.currency_id.id
        active_id = self.env.context.get(
            "active_model"
        ) == "sale.order" and self.env.context.get("active_id")
        if active_id:
            currency_id = self.env["sale.order"].browse(active_id).currency_id.id
        return f"""
            sale_order_log log
            JOIN sale_order so ON so.id = log.order_id
            JOIN res_partner partner ON so.partner_id = partner.id
            LEFT JOIN sale_order_close_reason close ON close.id=so.close_reason_id
            JOIN rate_query r1 ON r1.currency_id=so.currency_id
            JOIN rate_query r2 ON r2.currency_id={currency_id}
        """

    def _where(self):
        return """
            so.is_subscription
        """

    @property
    def _table_query(self):
        return self._query()

    def _query(self):
        return SQL(
            "WITH %s SELECT %s FROM %s WHERE %s",
            self._with(),
            SQL(self._select()),
            SQL(self._from()),
            SQL(self._where()),
        )

    def action_view_sale_order(self):
        self.check_singleton()
        if self.origin_order_id:
            action = self.order_id._get_associated_so_action()
            action["views"] = [
                (
                    self.env.ref(
                        "sale_subscription.sale_subscription_primary_form_view"
                    ).id,
                    "form",
                )
            ]
            orders = (
                self.env["sale.order"]
                .search(
                    [
                        "|",
                        ("origin_order_id", "=", self.origin_order_id.id),
                        ("id", "=", self.origin_order_id.id),
                    ]
                )
                .filtered(
                    lambda so: (
                        so.subscription_state in SUBSCRIPTION_PROGRESS_STATE + ["churn"]
                    )
                )
            )
            order_id = (orders and max(orders.ids)) or self.order_id.id
            action["res_id"] = order_id
            return action
        return {
            "res_model": self._name,
            "type": "ir.actions.act_window",
            "views": [[False, "form"]],
            "res_id": self.id,
        }

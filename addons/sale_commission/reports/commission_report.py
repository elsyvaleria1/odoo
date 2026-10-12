from datetime import date

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import SQL, frozendict

from odoo.addons.base.models.resource_utils import filter_domain_leaf


class SaleCommissionReport(models.Model):
    _name = "sale.commission.report"
    _search_visibility_fields = ()
    _description = "Sales Commission Report"
    _order = "id"
    _auto = False
    _depends = frozendict(
        {
            "sale.commission.plan": ["active", "company_id", "state", "type"],
            "sale.commission.plan.target": [
                "amount",
                "date_from",
                "date_to",
                "payment_date",
                "plan_id",
            ],
            "sale.commission.plan.target.commission": [
                "amount",
                "plan_id",
                "target_rate",
            ],
            "sale.commission.plan.target.forecast": [
                "amount",
                "notes",
                "target_id",
                "user_id",
            ],
            "sale.commission.plan.user": ["date_from", "date_to", "plan_id", "user_id"],
        }
    )
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    target_id = fields.Many2one(
        comodel_name="sale.commission.plan.target",
        string="Period",
        readonly=True,
    )
    target_amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    plan_id = fields.Many2one(
        comodel_name="sale.commission.plan",
        string="Commission Plan",
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Sales Person",
        readonly=True,
    )
    achieved = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    achieved_rate = fields.Float(
        readonly=True,
        aggregator="avg",
    )
    commission = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    forecast_id = fields.Many2one(
        comodel_name="sale.commission.plan.target.forecast",
        string="fc",
    )
    payment_date = fields.Date(readonly=True)
    forecast = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    date_from = fields.Date(related="target_id.date_from")
    date_to = fields.Date(related="target_id.date_to")
    notes = fields.Text(
        related="forecast_id.notes",
        readonly=True,
    )

    @api.model
    def web_search_read(
        self, domain, specification, offset=0, limit=None, order=None, count_limit=None
    ):
        return super().web_search_read(
            domain,
            specification,
            offset=offset,
            limit=limit,
            order=order,
            count_limit=count_limit,
        )

    web_search_read._readonly = False

    @api.model
    def formatted_read_group(
        self,
        domain,
        groupby=(),
        aggregates=(),
        having=(),
        offset=0,
        limit=None,
        order=None,
    ) -> list[dict]:
        return super().formatted_read_group(
            domain, groupby, aggregates, having, offset, limit, order
        )

    formatted_read_group._readonly = False

    @api.model
    def formatted_read_grouping_sets(
        self, domain, grouping_sets, aggregates=(), *, order=None
    ) -> list:
        return super().formatted_read_grouping_sets(
            domain,
            grouping_sets,
            aggregates,
            order=order,
        )

    formatted_read_grouping_sets._readonly = False

    @api.model
    def _search(self, domain, *args, **kwargs):
        model = self
        domain = Domain(domain)
        date_to_domain = filter_domain_leaf(
            domain, lambda field: "date_to" in field and "plan_id" not in field
        )
        date_to_domain = date_to_domain.optimize_full(model)
        date_to_list = [
            cond.value
            for cond in date_to_domain.iter_conditions()
            if isinstance(cond.value, date)
        ]
        if date_to_list:
            date_to = max(date_to_list)
            model = model.with_context(conversion_date=date_to.strftime("%Y-%m-%d"))
        return super(SaleCommissionReport, model)._search(domain, *args, **kwargs)

    def action_achievement_detail(self) -> dict:
        self.check_singleton()
        domain = [
            ("plan_id", "=", self.plan_id.id),
            ("user_id", "=", self.user_id.id),
        ]
        target_ids = self.plan_id.target_ids.filtered(
            lambda t: t.payment_date == self.target_id.payment_date
        )
        if target_ids:
            date_from = min(target_ids.mapped("date_from"))
            date_to = max(target_ids.mapped("date_to"))
            domain = Domain.AND(
                [
                    domain,
                    Domain([("date", ">=", date_from), ("date", "<=", date_to)]),
                ]
            )
        context = {
            "active_plan_ids": self.plan_id.ids,
            "active_target_ids": target_ids.ids,
        }
        if self.plan_id.user_type == "team":
            team_ids = self.env["team.team"].search(
                [("use_sale", "=", True), ("user_id", "=", self.user_id.id)]
            )
            context.update(
                {"commission_team_ids": self.user_id.sale_team_id.ids + team_ids.ids}
            )
        else:
            context.update({"commission_user_ids": self.user_id.ids})
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.commission.achievement.report",
            "name": self.env._("Commission Detail: %(name)s", name=self.target_id.name),
            "views": [
                [
                    self.env.ref(
                        "sale_commission.sale_achievement_report_view_list"
                    ).id,
                    "list",
                ]
            ],
            "context": context,
            "domain": domain,
        }

    def write(self, vals):
        if "forecast" in vals or "notes" in vals:
            forecast = vals.get("forecast")
            notes = vals.get("notes")
            for line in self:
                if line.forecast_id:
                    if forecast is not None:
                        line.sudo().forecast_id.amount = forecast
                    if notes:
                        line.sudo().forecast_id.notes = notes
                else:
                    line.forecast_id = (
                        self.env["sale.commission.plan.target.forecast"]
                        .sudo()
                        .create(
                            {
                                "target_id": line.target_id.id,
                                "amount": forecast or 0,
                                "plan_id": line.plan_id.id,
                                "user_id": line.user_id.id,
                                "notes": notes or False,
                            }
                        )
                    )
            if forecast:
                self._fields["forecast"]._get_cache(self.env).update(
                    dict.fromkeys(self.ids, forecast)
                )
            if notes:
                self._fields["notes"]._get_cache(self.env).update(
                    dict.fromkeys(self.ids, notes)
                )
        return True

    @property
    def _table_query(self):
        query = self._query()
        return SQL(query)

    def _query(self):
        users = self.env.context.get("commission_user_ids", [])
        if users:
            users = self.env["res.users"].browse(users).exists()
        teams = self.env.context.get("commission_team_ids", [])
        if teams:
            teams = self.env["team.team"].browse(teams).exists()
        achievement_view = self.env[
            "sale.commission.achievement.report"
        ]._get_report_view()
        if (
            not self.env["sale.commission.achievement.report"]._is_materialized_view()
            and achievement_view
        ):
            self.env.cr.execute(achievement_view)
        return f"""
WITH {self.env["sale.commission.achievement.report"]._get_currency_rate()},
commission_lines AS (
    SELECT id,
           target_id,
           user_id,
           team_id,
           achieved * cr.rate AS achieved,
           ca.currency_id,
           plan_company_id,
           achievement_company_id,
           plan_id,
           related_res_model,
           related_res_id,
           date,
           partner_id
FROM sale_commission_achievement_report_view ca
LEFT JOIN currency_rate cr
           ON cr.company_id = ca.achievement_company_id
), achievement AS (
    SELECT
        (
            COALESCE(era.plan_id, 0) * 10^11 +
            COALESCE(u.user_id, 0) +
            10^5 * COALESCE(to_char(era.date_from, 'YYMMDD')::integer, 0)
        )::bigint AS id,
        era.id AS target_id,
        era.plan_id AS plan_id,
        u.user_id AS user_id,
        MAX(scp.company_id) AS company_id,
        SUM(achieved) AS achieved,
        CASE
            WHEN MAX(era.amount) > 0 THEN GREATEST(SUM(achieved), 0) / (MAX(era.amount) * cr.rate)
            ELSE 0
        END AS achieved_rate,
        MAX(era.amount) AS amount,
        MAX(era.payment_date) AS payment_date,
        MAX(scpf.id) AS forecast_id,
        MAX(scpf.amount) AS forecast,
        MAX(scpf.notes) AS notes
        FROM sale_commission_plan_target era
        LEFT JOIN sale_commission_plan_user u
               ON u.plan_id=era.plan_id
              AND COALESCE(u.date_from, era.date_from)<era.date_to
              AND COALESCE(u.date_to, era.date_to)>era.date_from
        LEFT JOIN commission_lines cl
               ON cl.plan_id = era.plan_id
              AND cl.date::date >= era.date_from
              AND cl.date::date <= era.date_to
              AND cl.user_id = u.user_id
    LEFT JOIN sale_commission_plan_target_forecast scpf
           ON (scpf.target_id = era.id AND u.user_id = scpf.user_id)
    LEFT JOIN sale_commission_plan scp ON scp.id = u.plan_id
    LEFT JOIN currency_rate cr ON cr.company_id = scp.company_id
   WHERE scp.active
     AND scp.state = 'approved'
    GROUP BY
        era.id,
        era.plan_id,
        u.user_id,
        scp.company_id,
        cr.rate
), target_com AS (
    SELECT
        amount * cr.rate AS before,
        target_rate AS rate_low,
        LEAD(amount) OVER (PARTITION BY plan_id ORDER BY target_rate) * cr.rate AS amount,
        LEAD(target_rate) OVER (PARTITION BY plan_id ORDER BY target_rate) AS rate_high,
        plan_id
    FROM sale_commission_plan_target_commission scpta
    JOIN sale_commission_plan scp ON scp.id = scpta.plan_id
    LEFT JOIN currency_rate cr ON cr.company_id = scp.company_id
    WHERE scp.type = 'target'
), achievement_target AS (
    SELECT
        min(a.id) as id,
        min(a.target_id) as target_id,
        a.plan_id,
        a.user_id,
        a.company_id,
        {self.env.company.currency_id.id} AS currency_id,
        MIN(a.forecast_id) as forecast_id,
        MIN(a.payment_date) as payment_date,
        SUM(a.achieved) AS achieved,
        CASE WHEN SUM(a.amount) > 0 THEN SUM(a.achieved) / (SUM(a.amount) * cr.rate) ELSE 0.0 END AS achieved_rate,
        SUM(a.amount) * cr.rate AS target_amount,
        SUM(a.forecast) * cr.rate AS forecast,
        MAX(a.notes) AS notes,
        COUNT(1) AS ct
    FROM achievement a
    LEFT JOIN currency_rate cr ON cr.company_id = a.company_id
    GROUP BY
        a.plan_id, a.user_id, a.company_id, cr.rate, a.payment_date
)
SELECT
    a.*,
    CASE
        WHEN tc.before IS NULL THEN a.achieved
        WHEN tc.rate_high IS NULL THEN tc.before * a.ct
        ELSE (tc.before + (tc.amount - tc.before) * (a.achieved_rate - tc.rate_low) / (tc.rate_high - tc.rate_low)) * a.ct
    END AS commission
 FROM achievement_target a
    LEFT JOIN target_com tc ON (
        tc.plan_id = a.plan_id AND
        tc.rate_low <= a.achieved_rate AND
        (tc.rate_high IS NULL OR tc.rate_high > a.achieved_rate)
    )
"""

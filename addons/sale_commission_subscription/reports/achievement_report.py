from datetime import datetime

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleCommissionAchievementReport(models.Model):
    _inherit = "sale.commission.achievement.report"

    @api.model
    def _get_subscription_currency_rates(self) -> str:
        conversion_date = fields.Date.today()
        if self.env.context.get("conversion_date"):
            conversion_date = datetime.strptime(
                self.env.context["conversion_date"], "%Y-%m-%d"
            )
            _debug.logic("commission_conversion_date_replayed", date=conversion_date)
        rates = (
            self.env["res.currency"]
            ._select_companies_rates(date=conversion_date)
            .inlined(self.env.cr)
        )
        return f"""
            sub_rate_query AS (
                SELECT company_rates.currency_id,
                       company_rates.company_id,
                       company_rates.rate
                  FROM ({rates.code}) AS company_rates
        ),
        """

    @api.model
    def _get_filtered_order_log_cte(self, users=None, teams=None) -> str:
        date_from, date_to = self._get_achievement_default_dates()
        today = fields.Date.today().strftime("%Y-%m-%d")
        _debug.logic(
            "commission_log_filter",
            users=len(users) if users else 0,
            teams=len(teams) if teams else 0,
            date_from=date_from,
            date_to=date_to or today,
        )
        return f"""
        filtered_order_logs AS (
            SELECT
                    l.id,
                    l.order_id,
                    so.plan_id,
                    l.amount_signed,
                    so.team_id,
                    so.company_id,
                    so.user_id,
                    so.currency_id,
                    l.event_date,
                    l.date_effective,
                    l.create_date
              FROM sale_order_log l
              JOIN sale_order so ON so.id = l.order_id
             WHERE 1=1
               {"AND so.user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
               {"AND so.team_id in (%s)" % ",".join(str(i) for i in teams.ids) if teams else ""}
               {"AND l.event_date >= '%s' " % datetime.strftime(date_from, "%Y-%m-%d") if date_from else ""}
               AND l.event_date <= '{datetime.strftime(date_to, "%Y-%m-%d") if date_to else today}'
        ),
        """

    @api.model
    def _get_sale_order_log_rates(self) -> list:
        return ["mrr"]

    @api.model
    def _get_sale_order_log_product(self) -> str:
        return """
            rules.mrr_rate * log.amount_signed / COALESCE(log_rate.rate, 1)
        """

    @api.model
    def _select_rules(self):
        res = super()._select_rules()
        res += """
        ,scpa.recurring_plan_id
        """
        return res

    @api.model
    def _join_invoices(self, join_type=None):
        res = super()._join_invoices(join_type=join_type)
        res += """
          LEFT JOIN sale_order sub ON sub.id=aml.subscription_id
        """
        return res

    @api.model
    def _where_invoices(self):
        res = super()._where_invoices()
        res += """
          AND ((rules.recurring_plan_id IS NULL) OR (rules.recurring_plan_id=sub.plan_id))
        """
        return res

    def _subscription_lines(self, users=None, teams=None) -> tuple:
        return (
            f"""
{self._get_subscription_currency_rates()}
{self._get_filtered_order_log_cte(users=users, teams=teams)}
subscription_rules AS (
    SELECT
        COALESCE(scpu.date_from, scp.date_from) AS date_from,
        COALESCE(scpu.date_to, scp.date_to) AS date_to,
        scpu.user_id AS user_id,
        scp.team_id AS team_id,
        scp.id AS plan_id,
        scpa.recurring_plan_id,
        scp.company_id,
        scp_company.currency_id AS currency_to,
        scp.user_type = 'team' AS team_rule,
        {self._rate_to_case(self._get_sale_order_log_rates())}
    FROM sale_commission_plan_achievement scpa
    JOIN sale_commission_plan scp ON scp.id = scpa.plan_id
    JOIN res_company scp_company ON scp_company.id = scp.company_id
    JOIN sale_commission_plan_user scpu ON scpa.plan_id = scpu.plan_id
    WHERE scp.state = 'approved'
      AND scp.active
      AND scpa.type IN ({",".join("'%s'" % r for r in self._get_sale_order_log_rates())})
    {"AND scpu.user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
), subscription_commission_lines_team AS (
    SELECT
        rules.user_id,
        MAX(log.team_id) AS team_id,
        rules.plan_id,
        SUM({self._get_sale_order_log_product()}) AS achieved,
        {self.env.company.currency_id.id} AS currency_id,
        MAX(log.event_date) AS date,
        MAX(log.company_id) AS achievement_company_id,
        MAX(rules.company_id) AS plan_company_id,
        MAX(log.order_id) AS related_res_id,
        MAX(so.partner_id) AS partner_id,
        MAX(log.create_date) + (MAX(log.id) % 10) * INTERVAL '1 minute' AS entropy_date

    FROM subscription_rules rules
    JOIN filtered_order_logs log ON log.team_id=rules.team_id
    JOIN sale_order so ON so.id = log.order_id
    LEFT JOIN sub_rate_query log_rate ON log_rate.currency_id=log.currency_id AND log_rate.company_id=log.company_id
    WHERE rules.team_rule
      AND (rules.recurring_plan_id IS NULL OR log.plan_id = rules.recurring_plan_id)
      AND log.team_id = rules.team_id
    {"AND log.team_id in (%s)" % ",".join(str(i) for i in teams.ids) if teams else ""}
      AND log.event_date BETWEEN rules.date_from AND rules.date_to
      AND log.date_effective IS NOT NULL
    GROUP BY
        log.id,
        rules.plan_id,
        rules.user_id
), subscription_commission_lines_user AS (
    SELECT
        rules.user_id,
        MAX(log.team_id) AS team_id,
        rules.plan_id,
        SUM({self._get_sale_order_log_product()}) AS achieved,
        {self.env.company.currency_id.id} AS currency_id,
        MAX(log.event_date) AS date,
        MAX(log.company_id) AS achievement_company_id,
        MAX(rules.company_id) AS plan_company_id,
        MAX(log.order_id) AS related_res_id,
        MAX(so.partner_id) AS partner_id,
        -- create_date because _update_effective_date could update several logs at the same time
        -- transfers are created in the same transaction, we need to distinguish them too.
        -- We do it based on there id, generally they have very close id so modulo 10 is enough
        MAX(log.create_date) + (MAX(log.id) % 10) * INTERVAL '1 minute' AS entropy_date

    FROM subscription_rules rules
        JOIN filtered_order_logs log ON log.user_id=rules.user_id
    JOIN sale_order so ON so.id = log.order_id
    LEFT JOIN sub_rate_query log_rate ON log_rate.currency_id=log.currency_id AND log_rate.company_id=log.company_id
    WHERE NOT rules.team_rule
      AND (rules.recurring_plan_id IS NULL OR log.plan_id = rules.recurring_plan_id)
      AND log.user_id = rules.user_id
    {"AND log.user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
      AND log.event_date::DATE BETWEEN rules.date_from::DATE AND rules.date_to::DATE
      AND log.date_effective IS NOT NULL
    GROUP BY
        log.id,
        rules.plan_id,
        rules.user_id
), subscription_commission_lines AS (
    (SELECT *, 'sale.order' AS related_res_model FROM subscription_commission_lines_team)
    UNION ALL
    (SELECT *, 'sale.order' AS related_res_model FROM subscription_commission_lines_user)
)""",
            "subscription_commission_lines",
        )

    def _commission_lines_cte(self, users=None, teams=None):
        _debug.pipeline(
            "commission_subscription_cte_added",
            users=len(users) if users else 0,
            teams=len(teams) if teams else 0,
        )
        return super()._commission_lines_cte(users, teams) + [
            self._subscription_lines(users, teams)
        ]

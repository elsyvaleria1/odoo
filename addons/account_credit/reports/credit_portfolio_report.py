from odoo import fields, models
from odoo.tools import SQL

from ..models.credit_aging import AGING_CODES, aging_case_sql


class CreditPortfolioReport(models.Model):
    _name = "credit.portfolio.report"
    _description = "Credit Portfolio by Grade and Aging"
    _inherit = ["mixin.sql.report", "mixin.materialized.view"]
    _auto = False
    _relation_index_field = "id"
    _rec_name = "partner_id"
    _order = "amount_overdue desc"

    profile_id = fields.Many2one(
        comodel_name="credit.profile",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
    )
    grade_id = fields.Many2one(
        comodel_name="credit.grade",
        readonly=True,
    )
    state = fields.Char(readonly=True)
    score = fields.Float(
        readonly=True,
        aggregator="avg",
    )
    dbt_weighted = fields.Float(
        string="Days Beyond Terms",
        readonly=True,
        aggregator="avg",
    )
    exception_until = fields.Date(readonly=True)
    amount_open = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    amount_overdue = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    amount_current = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    amount_b1_30 = fields.Monetary(
        string="1-30 days",
        currency_field="currency_id",
        readonly=True,
    )
    amount_b31_60 = fields.Monetary(
        string="31-60 days",
        currency_field="currency_id",
        readonly=True,
    )
    amount_b61_90 = fields.Monetary(
        string="61-90 days",
        currency_field="currency_id",
        readonly=True,
    )
    amount_b91_180 = fields.Monetary(
        string="91-180 days",
        currency_field="currency_id",
        readonly=True,
    )
    amount_b180_plus = fields.Monetary(
        string="Over 180 days",
        currency_field="currency_id",
        readonly=True,
    )
    oldest_due_days = fields.Integer(
        readonly=True,
        aggregator="max",
    )
    expected_loss = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        help="Open receivable times the grade's expected loss rate.",
    )
    limit_amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )

    def _with_cte(self) -> SQL:
        bucket = aging_case_sql(
            "((now() AT TIME ZONE 'UTC')::date - COALESCE(l.date_maturity, l.date))"
        )
        return SQL(
            f"""
            receivable AS (
                SELECT p.id AS profile_id,
                       SUM(l.amount_residual) AS amount_open,
                       SUM(l.amount_residual) FILTER (WHERE l.amount_residual > 0 AND COALESCE(l.date_maturity, l.date) < (now() AT TIME ZONE 'UTC')::date) AS amount_overdue,
                       {
                " ".join(
                    f"SUM(l.amount_residual) FILTER (WHERE l.amount_residual > 0 AND {bucket} = '{code}') AS amount_{code},"
                    for code in AGING_CODES
                )
            }
                       MAX((now() AT TIME ZONE 'UTC')::date - COALESCE(l.date_maturity, l.date)) FILTER (WHERE l.amount_residual > 0 AND COALESCE(l.date_maturity, l.date) < (now() AT TIME ZONE 'UTC')::date) AS oldest_due_days
                  FROM credit_profile p
                  JOIN res_partner rp ON rp.commercial_partner_id = p.partner_id
                  JOIN account_move_line l ON l.partner_id = rp.id AND l.company_id = p.company_id
                  JOIN account_account a ON a.id = l.account_id
                 WHERE a.account_type = 'asset_receivable'
                   AND l.parent_state = 'posted'
                   AND l.reconciled IS NOT TRUE
                 GROUP BY p.id
            ),
            facility AS (
                SELECT f.profile_id, SUM(f.amount) AS amount
                  FROM credit_facility f
                 WHERE f.state = 'active'
                   AND f.date_start <= (now() AT TIME ZONE 'UTC')::date
                   AND (f.date_end IS NULL OR f.date_end >= (now() AT TIME ZONE 'UTC')::date)
                 GROUP BY f.profile_id
            )
            """
        )

    def _get_fields_select(self) -> dict:
        select = {
            "id": "p.id",
            "profile_id": "p.id",
            "partner_id": "p.partner_id",
            "company_id": "p.company_id",
            "currency_id": "c.currency_id",
            "grade_id": "COALESCE(p.grade_effective_id, p.grade_id)",
            "state": "p.state",
            "score": "p.score",
            "dbt_weighted": "p.dbt_weighted",
            "exception_until": "p.exception_until",
            "amount_open": "COALESCE(r.amount_open, 0)",
            "amount_overdue": "COALESCE(r.amount_overdue, 0)",
            "oldest_due_days": "COALESCE(r.oldest_due_days, 0)",
            "expected_loss": "COALESCE(r.amount_open, 0) * COALESCE(g.expected_loss_rate, 0) / 100.0",
            "limit_amount": "COALESCE(f.amount, 0)",
        }
        for code in AGING_CODES:
            select[f"amount_{code}"] = f"COALESCE(r.amount_{code}, 0)"
        return select

    def _get_from_tables(self) -> list:
        return [
            ("credit_profile", "p", None, None),
            ("res_company", "c", "JOIN", "c.id = p.company_id"),
            (
                "credit_grade",
                "g",
                "LEFT JOIN",
                "g.id = COALESCE(p.grade_effective_id, p.grade_id)",
            ),
            ("receivable", "r", "LEFT JOIN", "r.profile_id = p.id"),
            ("facility", "f", "LEFT JOIN", "f.profile_id = p.id"),
        ]

    def _get_where_conditions(self) -> list:
        return ["p.active"]

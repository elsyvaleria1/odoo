from datetime import datetime

from odoo import api, fields, models
from odoo.tools import frozendict

from odoo.addons.base.models.resource_utils import filter_domain_leaf

COMMISSION_LINE_COLUMNS = (
    "user_id",
    "team_id",
    "plan_id",
    "achieved",
    "currency_id",
    "date",
    "plan_company_id",
    "achievement_company_id",
    "related_res_id",
    "partner_id",
    "entropy_date",
    "related_res_model",
)


class SaleCommissionAchievementReport(models.Model):
    _name = "sale.commission.achievement.report"
    _search_visibility_fields = ()
    _description = "Sales Achievement Report"
    _order = "id"
    _auto = False
    _depends = frozendict(
        {
            "sale.commission.plan.target": ["amount", "payment_amount"],
        }
    )

    target_id = fields.Many2one(
        comodel_name="sale.commission.plan.target",
        string="Period",
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
    team_id = fields.Many2one(
        comodel_name="team.team",
        string="Sales Team",
        readonly=True,
    )
    achieved = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )

    target_amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    commission_target_amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        aggregator="avg",
        help="Sum of target amount per plan paid on the same date",
    )
    target_rate = fields.Float(
        string="Achieved Rate",
        readonly=True,
        aggregator="avg",
        help="Achieved over the target of that period, meaningless in group by",
    )
    commission_rate = fields.Float(
        readonly=True,
        aggregator="sum",
        help="Achieved over the commission target amount",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    date = fields.Date(readonly=True)
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        readonly=True,
    )

    related_res_model = fields.Char(readonly=True)
    related_res_id = fields.Many2oneReference(
        model_field="related_res_model",
        string="Related",
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
        date_to_domain = domain and filter_domain_leaf(
            domain, lambda field: "date_to" in field and "plan_id" not in field
        )
        date_to_list = date_to_domain and [
            datetime.strptime(d[2], "%Y-%m-%d")
            for d in date_to_domain
            if len(d) == 3 and d[2]
        ]
        model = self
        if date_to_list and "conversion_date" not in self.env.context:
            conversion_date = max(date_to_list)
            model = model.with_context(
                conversion_date=conversion_date.strftime("%Y-%m-%d")
            )
        return super(SaleCommissionAchievementReport, model)._search(
            domain, *args, **kwargs
        )

    def open_related(self) -> dict:
        return {
            "view_mode": "form",
            "res_model": self.related_res_model,
            "res_id": self.related_res_id,
            "type": "ir.actions.act_window",
        }

    @api.model
    def _get_achievement_default_dates(self) -> tuple:
        if self.env.context.get("active_plan_ids"):
            plan_ids = self.env["sale.commission.plan"].browse(
                self.env.context["active_plan_ids"]
            )
            date_from = plan_ids and min(plan_ids.mapped("date_from"))
            date_to = plan_ids and max(plan_ids.mapped("date_to"))
        else:
            all_plan_ids = self.env["sale.commission.plan"].search(
                [("state", "=", "approved")]
            )
            date_from = all_plan_ids and min(all_plan_ids.mapped("date_from"))
            date_to = all_plan_ids and max(all_plan_ids.mapped("date_to"))
        return date_from, date_to

    @api.model
    def _get_currency_rate(self) -> str:
        companies = self.env["res.company"].search([], order="id asc")
        current_company = self.env.company
        conversion_date = fields.Date.today()
        if self.env.context.get("conversion_date"):
            conversion_date = datetime.strptime(
                self.env.context["conversion_date"], "%Y-%m-%d"
            )
        currency_rate = [
            (
                current_company.id,
                current_company.currency_id.id,
                conversion_date.strftime("%Y-%m-%d"),
                1,
            )
        ]
        for comp in companies - current_company:
            rate = comp.currency_id._convert(
                from_amount=1,
                to_currency=current_company.currency_id,
                company=current_company,
                date=conversion_date,
                round=False,
            )
            currency_rate.append(
                (
                    comp.id,
                    comp.currency_id.id,
                    conversion_date.strftime("%Y-%m-%d"),
                    rate,
                )
            )
        return f"""currency_rate AS (
            SELECT * FROM (VALUES {", ".join(map(str, currency_rate))}) AS currency_values(company_id, currency_id, conversion_date,rate)
        )"""

    @property
    def _table_query(self):
        users = self.env.context.get("commission_user_ids", [])
        if users:
            users = self.env["res.users"].browse(users).exists()
        teams = self.env.context.get("commission_team_ids", [])
        if teams:
            teams = self.env["team.team"].browse(teams).exists()
        date_from, date_to = self.env[
            "sale.commission.achievement.report"
        ]._get_achievement_default_dates()
        today = fields.Date.today().strftime("%Y-%m-%d")
        date_from_condition = (
            f"""AND date >= '{datetime.strftime(date_from, "%Y-%m-%d")}'"""
            if date_from
            else ""
        )
        achievement_view = self._get_report_view()
        if not self._is_materialized_view() and achievement_view:
            self.env.cr.execute(achievement_view)
        return f"""
        WITH {self._get_currency_rate()}
        SELECT cl.id AS id,
               cl.target_id,
               cl.user_id,
               cl.team_id,
               cl.achieved * cr.rate AS achieved,
               {self.env.company.currency_id.id} AS currency_id,
               cl.plan_company_id as company_id,
               cl.achievement_company_id as achievement_company_id,
               cl.plan_id,
               cl.related_res_model,
               cl.related_res_id,
               cl.date,
               cl.partner_id,
               era.amount * cr.rate AS target_amount,
               era.payment_amount * cr.rate AS commission_target_amount,
               CASE
                   WHEN era.amount IS NULL OR era.amount = 0 THEN 0
                   ELSE cl.achieved / (era.amount * cr.rate)
               END as target_rate,
               CASE
                   WHEN era.payment_amount IS NULL OR era.payment_amount = 0 THEN 0
                   ELSE cl.achieved / (era.payment_amount * cr.rate)
               END as commission_rate
          FROM sale_commission_achievement_report_view cl
          JOIN sale_commission_plan_target era ON era.id = cl.target_id
         JOIN currency_rate cr ON cr.company_id = cl.achievement_company_id
        WHERE 1=1
        {"AND user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
        {"AND team_id in (%s)" % ",".join(str(i) for i in teams.ids) if teams else ""}
        {date_from_condition}
        AND date <= '{datetime.strftime(date_to, "%Y-%m-%d") if date_to else today}'
        """


    def _get_view_parameters(self) -> str:
        return "TEMPORARY"

    def _view_post_creation(self) -> str:
        return ""

    def _is_materialized_view(self) -> bool:
        return False

    def _get_report_view(self) -> str | None:
        self.env.cr.execute("""
            SELECT 1 FROM pg_catalog.pg_class AS c
                WHERE c.relname = 'sale_commission_achievement_report_view'
                AND c.relkind = 'v'::"char"
                AND pg_catalog.pg_table_is_visible(c.oid)
        """)
        res = self.env.cr.fetchone()
        if res:
            return None
        return f"""
            CREATE {self._get_view_parameters()} VIEW sale_commission_achievement_report_view AS
              WITH {self._commission_lines_query(users=None, teams=None)}
            SELECT
                    (cl.plan_id *10^13 + cl.related_res_id * 10^5 + 10^3 * LENGTH(cl.related_res_model) + cl.user_id + TO_CHAR(entropy_date, 'YYYYMMDDHH24MISS')::bigint + TO_CHAR(cl.date, 'YYMMDD')::integer)::bigint  AS id,
                    era.id AS target_id,
                    cl.user_id AS user_id,
                    cl.team_id AS team_id,
                    cl.achieved AS achieved,
                    cl.currency_id AS currency_id,
                    -- company_id is the company of the achivement, used for currency conversion
                    cl.plan_company_id AS plan_company_id,
                    cl.achievement_company_id as achievement_company_id,
                    cl.plan_id,
                    cl.related_res_model,
                    cl.related_res_id::INTEGER AS related_res_id,
                    cl.date::date AS date,
                    cl.partner_id::INTEGER AS partner_id
              FROM commission_lines cl
              JOIN sale_commission_plan_target era
                ON cl.plan_id = era.plan_id
               AND cl.date::date >= era.date_from
               AND cl.date::date <= era.date_to;
            {self._view_post_creation()}
        """


    @api.model
    def _rate_to_case(self, rates) -> str:
        case = "CASE WHEN scpa.type = '%s' THEN rate ELSE 0 END AS %s"
        return ",\n".join(case % (s, s + "_rate") for s in rates)

    @api.model
    def _get_sale_rates(self):
        return ["amount_sold", "qty_sold"]

    @api.model
    def _get_invoices_rates(self) -> list:
        return ["amount_invoiced", "qty_invoiced"]

    @api.model
    def _get_sale_rates_product(self):
        return """
            rules.amount_sold_rate * sol.price_subtotal / fo.currency_rate +
            rules.qty_sold_rate * sol.product_uom_qty
        """

    @api.model
    def _get_filtered_orders_cte(self, users=None, teams=None) -> str:
        date_from, date_to = self._get_achievement_default_dates()
        today = fields.Date.today().strftime("%Y-%m-%d")
        date_from_condition = (
            f"""AND date_order >= '{datetime.strftime(date_from, "%Y-%m-%d")}'"""
            if date_from
            else ""
        )
        return f"""
        filtered_orders AS (
            SELECT
                    id,
                    team_id,
                    state,
                    currency_rate,
                    company_id,
                    currency_id,
                    user_id,
                    date_order,
                    write_date,
                    partner_id
              FROM sale_order
             WHERE sale_order.state::TEXT = 'done'::TEXT
               {"AND user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
               {"AND team_id in (%s)" % ",".join(str(i) for i in teams.ids) if teams else ""}
               {date_from_condition}
               AND date_order <= '{datetime.strftime(date_to, "%Y-%m-%d") if date_to else today}'
        )
        """

    @api.model
    def _get_filtered_moves_cte(self, users=None, teams=None) -> str:
        date_from, date_to = self._get_achievement_default_dates()
        today = fields.Date.today().strftime("%Y-%m-%d")
        date_from_str = date_from and datetime.strftime(date_from, "%Y-%m-%d")
        date_from_condition = (
            f"""AND date >= '{date_from_str}'""" if date_from_str else ""
        )
        return f"""
        filtered_moves AS (
            SELECT
                    id,
                    team_id,
                    move_type,
                    state,
                    invoice_currency_rate,
                    company_id,
                    currency_id,
                    invoice_user_id,
                    date,
                    write_date,
                    partner_id
              FROM account_move
             WHERE move_type IN ('out_invoice', 'out_refund')
               AND state = 'posted'
             {"AND invoice_user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
             {"AND team_id in (%s)" % ",".join(str(i) for i in teams.ids) if teams else ""}
               {date_from_condition}
               AND date <= '{datetime.strftime(date_to, "%Y-%m-%d") if date_to else today}'
        )
        """

    @api.model
    def _get_invoice_rates_product(self) -> str:
        return """
        CASE
            WHEN fm.move_type = 'out_invoice' THEN
                rules.amount_invoiced_rate * aml.price_subtotal / fm.invoice_currency_rate +
                rules.qty_invoiced_rate * aml.quantity
            WHEN fm.move_type = 'out_refund' THEN
                (rules.amount_invoiced_rate * aml.price_subtotal / fm.invoice_currency_rate +
                rules.qty_invoiced_rate * aml.quantity) * -1
        END
        """

    @api.model
    def _select_invoices(self) -> str:
        return f"""
          rules.user_id AS user_id, -- rule user to work with team commission
          MAX(fm.team_id) AS team_id,
          rules.plan_id,
          SUM({self._get_invoice_rates_product()}) AS achieved,
          MAX(fm.currency_id) AS currency_id,
          MAX(fm.date) AS date,
          MAX(rules.company_id) AS plan_company_id,
          MAX(fm.company_id) AS achievement_company_id,
          fm.id AS related_res_id,
          MAX(fm.partner_id) AS partner_id,
          MAX(fm.write_date) as entropy_date
        """

    @api.model
    def _join_invoices(self, join_type=None):
        if join_type == "team":
            jointure = "fm.team_id = rules.team_id"
        else:
            jointure = "fm.invoice_user_id = rules.user_id"
        return f"""
          JOIN filtered_moves fm ON {jointure}
          JOIN account_move_line aml
            ON aml.move_id = fm.id
          LEFT JOIN product_product pp
            ON aml.product_id = pp.id
          LEFT JOIN product_template pt
            ON pp.product_tmpl_id = pt.id
        """

    @api.model
    def _where_invoices(self):
        return """
          aml.display_type = 'product'
          AND fm.move_type in ('out_invoice', 'out_refund')
          AND fm.state = 'posted'
        """

    @api.model
    def _select_rules(self):
        return ""

    @api.model
    def _select_sales(self) -> str:
        return """
          fo.id AS related_res_id,
          MAX(fo.partner_id) AS partner_id,
          MAX(fo.write_date) as entropy_date
        """

    @api.model
    def _join_sales(self, join_type=None) -> str:
        if join_type == "team":
            jointure = "fo.team_id = rules.team_id"
        else:
            jointure = "fo.user_id = rules.user_id"
        return f"""
        JOIN filtered_orders fo ON {jointure}
        JOIN sale_order_line sol
          ON sol.order_id = fo.id
        """

    @api.model
    def _where_sales(self) -> str:
        return """
          AND sol.display_type IS NULL
          AND (fo.date_order BETWEEN rules.date_from AND rules.date_to)
          AND fo.state::TEXT = 'done'::TEXT
          AND (rules.product_id IS NULL OR rules.product_id = sol.product_id)
          AND (rules.product_categ_id IS NULL OR rules.product_categ_id = pt.categ_id)
          AND COALESCE(sol.is_expense, false) = false
          AND COALESCE(sol.is_downpayment, false) = false
        """

    @api.model
    def _get_filtered_achivement_cte(self, users=None, teams=None) -> str:
        date_from = None
        date_to = None
        if self.env.context.get("active_target_ids"):
            target_ids = self.env["sale.commission.plan.target"].browse(
                self.env.context["active_target_ids"]
            )
            date_from = min(target_ids.mapped("date_from"))
            date_to = max(target_ids.mapped("date_to"))

        elif self.env.context.get("active_plan_ids"):
            plan_ids = self.env["sale.commission.plan"].browse(
                self.env.context["active_plan_ids"]
            )
            date_from = min(plan_ids.mapped("date_from"))
            date_to = max(plan_ids.mapped("date_to"))
        today = fields.Date.today().strftime("%Y-%m-%d")
        date_from_str = date_from and datetime.strftime(date_from, "%Y-%m-%d")
        date_from_condition = (
            f"""AND date >= '{date_from_str}'""" if date_from_str else ""
        )
        return f"""
        filtered_adjustments AS (
            SELECT
                    a.id,
                    add_user_id,
                    reduce_user_id,
                    company_id,
                    currency_id,
                    currency_rate,
                    achieved,
                    date,
                    write_date
              FROM sale_commission_achievement a
              WHERE 1=1
             {date_from_condition}
               AND date <= '{datetime.strftime(date_to, "%Y-%m-%d") if date_to else today}'
        )
        """

    def _achievement_lines_add(self, users=None, teams=None) -> tuple:
        return (
            f"""
{self._get_filtered_achivement_cte(users=users, teams=teams)},
achievement_commission_lines_add AS (
    SELECT
        scpu.user_id AS user_id,
        scp.team_id AS team_id,
        scp.id AS plan_id,
        fa.achieved / fa.currency_rate AS achieved,
        fa.currency_id AS currency_id,
        fa.date AS date,
        scp.company_id AS plan_company_id,
        scp.company_id AS achievement_company_id,
        fa.id AS related_res_id,
        -- achievement don't involve a customer; needed to match UNION structure with other sources
        NULL::integer AS partner_id,
        MAX(fa.write_date) +  INTERVAL '1 minute' + MAX(fa.id) * INTERVAL '1 minute' AS entropy_date,
        'sale.commission.achievement' AS related_res_model
    FROM filtered_adjustments fa
    JOIN sale_commission_plan_user scpu ON scpu.id = fa.add_user_id
    JOIN sale_commission_plan scp ON scpu.plan_id = scp.id
    WHERE scp.active
      AND scp.state = 'approved'
      {"AND scpu.user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
    GROUP BY scpu.user_id,
             scp.team_id,
             scp.id,
             fa.currency_id,
             fa.currency_rate,
             fa.achieved,
             fa.date,
             scp.company_id,
             fa.id
)
""",
            "achievement_commission_lines_add",
        )

    def _achievement_lines_rem(self, users=None, teams=None) -> tuple:
        return (
            f"""
achievement_commission_lines_rem AS (
    SELECT
        scpu.user_id AS user_id,
        scp.team_id AS team_id,
        scp.id AS plan_id,
        - fa.achieved / fa.currency_rate AS achieved,
        fa.currency_id AS currency_id,
        fa.date AS date,
        scp.company_id AS plan_company_id,
        scp.company_id AS achievement_company_id,
        fa.id AS related_res_id,
        -- achievement don't involve a customer; needed to match UNION structure with other sources
        NULL::integer AS partner_id,
        MAX(fa.write_date) -  INTERVAL '1 minute' + MAX(fa.id) * INTERVAL '1 minute' AS entropy_date,
        'sale.commission.achievement' AS related_res_model
    FROM filtered_adjustments fa
    JOIN sale_commission_plan_user scpu ON scpu.id = fa.reduce_user_id
    JOIN sale_commission_plan scp ON scpu.plan_id = scp.id
    WHERE scp.active
      AND scp.state = 'approved'
      {"AND scpu.user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
    GROUP BY scpu.user_id,
             scp.team_id,
             scp.id,
             fa.currency_rate,
             fa.achieved,
             fa.date,
             scp.company_id,
             fa.currency_id,
             fa.id
)
""",
            "achievement_commission_lines_rem",
        )

    def _invoices_lines(self, users=None, teams=None) -> tuple:
        return (
            f"""
{self._get_filtered_moves_cte(users=users, teams=teams)},
invoices_rules AS (
    SELECT
        COALESCE(scpu.date_from, scp.date_from) AS date_from,
        COALESCE(scpu.date_to, scp.date_to) AS date_to,
        scpu.user_id AS user_id,
        scp.team_id AS team_id,
        scp.id AS plan_id,
        scpa.product_id,
        scpa.product_categ_id,
        scp.company_id,
        scp_company.currency_id AS currency_id,
        scp.user_type = 'team' AS team_rule,
        {self._rate_to_case(self._get_invoices_rates())}
        {self._select_rules()}
    FROM sale_commission_plan_achievement scpa
    JOIN sale_commission_plan scp ON scp.id = scpa.plan_id
    JOIN res_company scp_company ON scp_company.id = scp.company_id
    JOIN sale_commission_plan_user scpu ON scpa.plan_id = scpu.plan_id
    WHERE scp.active
      AND scp.state = 'approved'
      AND scpa.type IN ({",".join("'%s'" % r for r in self._get_invoices_rates())})
    {"AND scpu.user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
),
invoice_commission_lines_team AS (
    SELECT
        {self._select_invoices()}
    FROM invoices_rules rules
         {self._join_invoices(join_type="team")}
    WHERE {self._where_invoices()}
      AND rules.team_rule
      AND fm.team_id = rules.team_id
    {"AND fm.team_id in (%s)" % ",".join(str(i) for i in teams.ids) if teams else ""}
      AND fm.date BETWEEN rules.date_from AND rules.date_to
      AND (rules.product_id IS NULL OR rules.product_id = aml.product_id)
      AND (rules.product_categ_id IS NULL OR rules.product_categ_id = pt.categ_id)
    GROUP BY
        fm.id,
        rules.plan_id,
        rules.user_id
), invoice_commission_lines_user AS (
    SELECT
          {self._select_invoices()}
    FROM invoices_rules rules
         {self._join_invoices(join_type="user")}
    WHERE {self._where_invoices()}
      AND NOT rules.team_rule
      AND fm.invoice_user_id = rules.user_id
    {"AND fm.invoice_user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
      AND fm.date BETWEEN rules.date_from AND rules.date_to
      AND (rules.product_id IS NULL OR rules.product_id = aml.product_id)
      AND (rules.product_categ_id IS NULL OR rules.product_categ_id = pt.categ_id)
    GROUP BY
        fm.id,
        rules.plan_id,
        rules.user_id
), invoice_commission_lines AS (
    (SELECT *, 'account.move' AS related_res_model FROM invoice_commission_lines_team)
    UNION ALL
    (SELECT *, 'account.move' AS related_res_model FROM invoice_commission_lines_user)
)""",
            "invoice_commission_lines",
        )

    def _sale_lines(self, users=None, teams=None) -> tuple:
        return (
            f"""
{self._get_filtered_orders_cte(users=users, teams=teams)},
sale_rules AS (
    SELECT
        COALESCE(scpu.date_from, scp.date_from) AS date_from,
        COALESCE(scpu.date_to, scp.date_to) AS date_to,
        scpu.user_id AS user_id,
        scp.team_id AS team_id,
        scp.id AS plan_id,
        scpa.product_id,
        scpa.product_categ_id,
        scp.company_id,
        scp_company.currency_id AS currency_id,
        scp.user_type = 'team' AS team_rule,
        {self._rate_to_case(self._get_sale_rates())}
        {self._select_rules()}
    FROM sale_commission_plan_achievement scpa
    JOIN sale_commission_plan scp ON scp.id = scpa.plan_id
    JOIN res_company scp_company ON scp_company.id = scp.company_id
    JOIN sale_commission_plan_user scpu ON scpa.plan_id = scpu.plan_id
    WHERE scp.active
      AND scp.state = 'approved'
      AND scpa.type IN ({",".join("'%s'" % r for r in self._get_sale_rates())})
    {"AND scpu.user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
), sale_commission_lines_team AS (
    SELECT
        rules.user_id,
        MAX(rules.team_id) AS team_id,
        rules.plan_id,
        SUM({self._get_sale_rates_product()}) AS achieved,
        MAX(fo.currency_id) AS currency_id,
        MAX(fo.date_order) AS date,
        MAX(rules.company_id) AS plan_company_id,
        MAX(fo.company_id) AS achievement_company_id,
        {self._select_sales()}
    FROM sale_rules rules
    {self._join_sales(join_type="team")}
    JOIN product_product pp
      ON sol.product_id = pp.id
    JOIN product_template pt
      ON pp.product_tmpl_id = pt.id
    WHERE rules.team_rule
      AND fo.team_id = rules.team_id
    {"AND fo.team_id in (%s)" % ",".join(str(i) for i in teams.ids) if teams else ""}
    {self._where_sales()}
    GROUP BY
        fo.id,
        rules.plan_id,
        rules.user_id
), sale_commission_lines_user AS (
    SELECT
        rules.user_id,
        MAX(fo.team_id) AS team_id,
        rules.plan_id,
        SUM({self._get_sale_rates_product()}) AS achieved,
        MAX(fo.currency_id) AS currency_id,
        MAX(fo.date_order) AS date,
        MAX(rules.company_id) AS plan_company_id,
        MAX(fo.company_id) AS achievement_company_id,
        {self._select_sales()}
    FROM sale_rules rules
    {self._join_sales(join_type="user")}
    JOIN product_product pp
      ON sol.product_id = pp.id
    JOIN product_template pt
      ON pp.product_tmpl_id = pt.id
    WHERE NOT rules.team_rule
      AND fo.user_id = rules.user_id
    {"AND fo.user_id in (%s)" % ",".join(str(i) for i in users.ids) if users else ""}
      {self._where_sales()}
    GROUP BY
        fo.id,
        rules.plan_id,
        rules.user_id
), sale_commission_lines AS (
    (SELECT *, 'sale.order' AS related_res_model FROM sale_commission_lines_team)
    UNION ALL
    (SELECT *, 'sale.order' AS related_res_model FROM sale_commission_lines_user)
)""",
            "sale_commission_lines",
        )

    def _commission_lines_cte(self, users=None, teams=None):
        return [
            self._achievement_lines_add(users, teams),
            self._achievement_lines_rem(users, teams),
            self._sale_lines(users, teams),
            self._invoices_lines(users, teams),
        ]

    def _commission_lines_query(self, users=None, teams=None) -> str:
        ctes = self._commission_lines_cte(users, teams)
        queries = [x[0] for x in ctes]
        table_names = [x[1] for x in ctes]
        columns = ", ".join(COMMISSION_LINE_COLUMNS)
        return f"""
{",".join(queries)},
commission_lines AS (
    {" UNION ALL ".join(f"(SELECT {columns} FROM {name})" for name in table_names)}
)
"""

    def _pre_achievement_operation(self) -> None:
        self.env.flush_all()
        self.env.invalidate_all()

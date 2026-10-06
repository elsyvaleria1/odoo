from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.tools import frozendict


class EsgEmployeeCommutingReport(models.Model):
    _name = "esg.employee.commuting.report"
    _description = "ESG Employee Commuting Report"
    _auto = False
    _depends = frozendict(
        {
            "hr.employee": ["distance_home_work", "resource_id"],
            "product.product": ["product_tmpl_id"],
            "product.template": ["co2"],
            "res.company": ["weekly_days_at_office"],
            "resource.asset.vehicle": ["company_id", "product_id", "resource_id"],
            "resource.assignment": [
                "active",
                "assignee_id",
                "custody_role",
                "date_end",
                "date_start",
                "resource_id",
            ],
        }
    )

    driver_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    vehicle_id = fields.Many2one(
        comodel_name="resource.asset.vehicle",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    date_from = fields.Date(
        string="Date",
        readonly=True,
    )
    date_to = fields.Date(readonly=True)
    co2 = fields.Float(
        string="gCO₂/km",
        readonly=True,
    )
    total_distance = fields.Float(
        string="km",
        readonly=True,
    )
    total_co2 = fields.Float(
        string="tCO₂",
        readonly=True,
    )

    def init(self) -> None:
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW esg_employee_commuting_report AS (
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY log.vehicle_id, log.driver_id, month_start
                    ) AS id,
                    log.vehicle_id,
                    log.driver_id,
                    log.company_id,
                    rc.weekly_days_at_office,
                    month_start::DATE AS date_from,
                    (month_start + INTERVAL '1 month - 1 day')::DATE AS date_to,
                    log.co2,
                    SUM(
                        log.distance_home_work * 2 * (
                            EXTRACT(DAY FROM (
                                LEAST(month_start + INTERVAL '1 month - 1 day', COALESCE(log.date_end, NOW() AT TIME ZONE 'utc'))
                                - GREATEST(month_start, log.date_start)
                            )) + 1
                        ) * log.co2 / 1e6
                    ) * rc.weekly_days_at_office / 7 AS total_co2,
                    SUM(
                        log.distance_home_work * 2 * (
                            EXTRACT(DAY FROM (
                                LEAST(month_start + INTERVAL '1 month - 1 day', COALESCE(log.date_end, NOW() AT TIME ZONE 'utc'))
                                - GREATEST(month_start, log.date_start)
                            )) + 1
                        )
                    ) * rc.weekly_days_at_office / 7 AS total_distance
                FROM (
                    SELECT v.id AS vehicle_id,
                           e.id AS driver_id,
                           v.company_id,
                           COALESCE(t.co2, 0) AS co2,
                           e.distance_home_work,
                           date_trunc('day', a.date_start) AS date_start,
                           date_trunc('day', a.date_end) AS date_end
                      FROM resource_assignment a
                      JOIN resource_asset_vehicle v ON v.resource_id = a.resource_id
                      JOIN hr_employee e ON e.resource_id = a.assignee_id
                      LEFT JOIN product_product p ON p.id = v.product_id
                      LEFT JOIN product_template t ON t.id = p.product_tmpl_id
                     WHERE a.custody_role = 'operator' AND a.active
                ) log
                JOIN res_company rc ON rc.id = log.company_id
                JOIN LATERAL (SELECT generate_series(
                    date_trunc('month', log.date_start),
                    date_trunc('month', COALESCE(log.date_end, NOW() AT TIME ZONE 'utc')),
                    '1 month'::INTERVAL
                )) g(month_start) ON TRUE
                GROUP BY
                    log.driver_id,
                    log.vehicle_id,
                    log.company_id,
                    month_start,
                    log.co2,
                    log.distance_home_work,
                    rc.weekly_days_at_office
            )
        """)

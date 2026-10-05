from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.tools import SQL, frozendict


class AssetTripReport(models.Model):
    _name = "asset.trip.report"
    _description = "Vehicle Trip Report"
    _auto = False
    _depends = frozendict(
        {
            "device.data.log.gps": [
                "device_id",
                "real_odometer",
                "odometer_valid",
                "timestamp",
            ],
            "hr.attendance": ["check_in", "check_out", "employee_id"],
            "hr.department": ["name"],
            "hr.employee": ["company_id", "current_version_id", "name", "resource_id"],
            "hr.version": ["department_id"],
            "resource.asset.vehicle": ["license_plate", "resource_id"],
            "resource.resource": ["fuel_cost_per_km", "kind_id", "name", "tz"],
            "resource.gps.binding": [
                "resource_id",
                "device_id",
                "company_id",
                "date_start",
                "date_end",
            ],
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
    _order = "date_start desc"

    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )

    operator_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    operator_name = fields.Char(readonly=True)
    department_id = fields.Many2one(
        comodel_name="hr.department",
        readonly=True,
    )
    department_name = fields.Char(readonly=True)

    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        readonly=True,
    )
    asset_name = fields.Char(readonly=True)
    license_plate = fields.Char(readonly=True)

    device_id = fields.Many2one(
        comodel_name="device.device",
        readonly=True,
    )

    date_start = fields.Datetime(readonly=True)
    date_start_local = fields.Char(
        readonly=True,
        help="Start date and time in local timezone (24h format)",
    )
    weekday_start = fields.Char(readonly=True)
    date_end = fields.Datetime(readonly=True)
    date_end_local = fields.Char(
        readonly=True,
        help="End date and time in local timezone (24h format)",
    )
    weekday_end = fields.Char(readonly=True)

    duration_hours = fields.Float(
        digits=(10, 2),
        readonly=True,
    )

    odometer_start = fields.Float(
        digits=(12, 2),
        readonly=True,
    )
    odometer_end = fields.Float(
        digits=(12, 2),
        readonly=True,
    )
    distance = fields.Float(
        digits=(10, 2),
        readonly=True,
    )
    work_hours_status = fields.Char(
        readonly=True,
        help="Whether the trip was during or outside work hours",
    )

    fuel_cost_per_km = fields.Float(
        digits=(12, 2),
        readonly=True,
        help="Fuel cost per kilometer configured on the vehicle",
    )
    fuel_amount = fields.Float(
        digits=(12, 2),
        readonly=True,
        help="Distance times the vehicle's fuel cost per kilometer",
    )

    def _query(self):
        return SQL(
            """
            WITH
            -- Every operator assignment the ledger holds, ended or live, so a
            -- period stays with the operator who held the vehicle at the time
            vehicle_operator_history AS (
                SELECT
                    a.id AS asset_id,
                    ra.device_id,
                    ra.company_id,
                    e.id AS operator_id,
                    ra.date_start,
                    ra.date_end
                FROM (%(custody_periods)s) ra
                JOIN resource_resource a ON a.id = ra.resource_id AND a.kind_id IS NOT NULL
                JOIN hr_employee e ON e.resource_id = ra.assignee_id
                WHERE ra.custody_role = 'operator'
                  AND e.company_id = ra.company_id
            ),
            -- Get attendance records with next check_in using LEAD
            attendance_periods AS (
                SELECT
                    ha.id AS attendance_id,
                    ha.employee_id,
                    ha.check_in,
                    ha.check_out,
                    LEAD(ha.check_in) OVER (
                        PARTITION BY ha.employee_id
                        ORDER BY ha.check_in
                    ) AS next_check_in
                FROM hr_attendance ha
                WHERE ha.check_out IS NOT NULL
            ),
            -- Create 2 records per attendance: In hours + Out of hours
            periods AS (
                -- In hours: check_in → check_out
                SELECT
                    ap.attendance_id,
                    ap.employee_id,
                    ap.check_in AS date_start,
                    ap.check_out AS date_end,
                    'In hours' AS work_hours_status
                FROM attendance_periods ap

                UNION ALL

                -- Out of hours: check_out → next check_in
                SELECT
                    ap.attendance_id,
                    ap.employee_id,
                    ap.check_out AS date_start,
                    ap.next_check_in AS date_end,
                    'Out of hours' AS work_hours_status
                FROM attendance_periods ap
                WHERE ap.next_check_in IS NOT NULL
            )
            -- Final SELECT with vehicle/operator info and GPS distance
            SELECT
                (ROW_NUMBER() OVER (ORDER BY clip.date_start DESC))::integer AS id,
                voh.device_id,
                voh.company_id,
                a.id AS asset_id,
                tracked_resource.name AS asset_name,
                a.license_plate,
                voh.operator_id AS operator_id,
                he.name AS operator_name,
                hv.department_id AS department_id,
                hd.name ->> 'en_US' AS department_name,
                clip.date_start,
                clip.date_end,
                TO_CHAR(
                    clip.date_start AT TIME ZONE 'UTC' AT TIME ZONE tracked_resource.tz,
                    'DD/MM/YYYY HH24:MI'
                ) AS date_start_local,
                TO_CHAR(
                    clip.date_end AT TIME ZONE 'UTC' AT TIME ZONE tracked_resource.tz,
                    'DD/MM/YYYY HH24:MI'
                ) AS date_end_local,
                CASE EXTRACT(DOW FROM clip.date_start AT TIME ZONE 'UTC' AT TIME ZONE tracked_resource.tz)
                    WHEN 0 THEN 'Sunday'
                    WHEN 1 THEN 'Monday'
                    WHEN 2 THEN 'Tuesday'
                    WHEN 3 THEN 'Wednesday'
                    WHEN 4 THEN 'Thursday'
                    WHEN 5 THEN 'Friday'
                    WHEN 6 THEN 'Saturday'
                END AS weekday_start,
                CASE EXTRACT(DOW FROM clip.date_end AT TIME ZONE 'UTC' AT TIME ZONE tracked_resource.tz)
                    WHEN 0 THEN 'Sunday'
                    WHEN 1 THEN 'Monday'
                    WHEN 2 THEN 'Tuesday'
                    WHEN 3 THEN 'Wednesday'
                    WHEN 4 THEN 'Thursday'
                    WHEN 5 THEN 'Friday'
                    WHEN 6 THEN 'Saturday'
                END AS weekday_end,
                EXTRACT(EPOCH FROM (clip.date_end - clip.date_start)) / 3600.0 AS duration_hours,
                COALESCE(gps.odometer_start, 0) AS odometer_start,
                COALESCE(gps.odometer_end, 0) AS odometer_end,
                GREATEST(COALESCE(gps.odometer_end, 0) - COALESCE(gps.odometer_start, 0), 0) AS distance,
                p.work_hours_status,
                COALESCE(tracked_resource.fuel_cost_per_km, 0) AS fuel_cost_per_km,
                GREATEST(COALESCE(gps.odometer_end, 0) - COALESCE(gps.odometer_start, 0), 0)
                    * COALESCE(tracked_resource.fuel_cost_per_km, 0) AS fuel_amount
            FROM periods p
            -- Join with operator-vehicle history based on date overlap
            JOIN vehicle_operator_history voh
                ON voh.operator_id = p.employee_id
                AND p.date_end > voh.date_start
                AND (voh.date_end IS NULL OR p.date_start < voh.date_end)
            JOIN resource_asset_vehicle a ON voh.asset_id = a.id
                AND a.license_plate IS NOT NULL
            JOIN hr_employee he ON he.id = voh.operator_id
            LEFT JOIN hr_version hv ON hv.id = he.current_version_id
            LEFT JOIN hr_department hd ON hd.id = hv.department_id
            JOIN resource_resource tracked_resource ON tracked_resource.id = a.resource_id
            CROSS JOIN LATERAL (
                SELECT GREATEST(p.date_start, voh.date_start) AS date_start,
                       LEAST(p.date_end, voh.date_end) AS date_end
            ) clip
            -- Aggregate GPS distance for the period (MIN/MAX odometer)
            LEFT JOIN LATERAL (
                SELECT
                    MIN(log.real_odometer) AS odometer_start,
                    MAX(log.real_odometer) AS odometer_end
                FROM device_data_log_gps log
                WHERE log.device_id = voh.device_id
                  AND log.timestamp >= clip.date_start
                  AND log.timestamp < clip.date_end
                  AND log.real_odometer > 0
                  AND log.odometer_valid
            ) gps ON TRUE
            WHERE clip.date_start < clip.date_end
        """,
            custody_periods=self.env["resource.gps.binding"]._custody_query(),
        )

    def init(self) -> None:
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            SQL(
                "CREATE OR REPLACE VIEW %s AS (%s)",
                SQL.identifier(self._table),
                self._query(),
            )
        )

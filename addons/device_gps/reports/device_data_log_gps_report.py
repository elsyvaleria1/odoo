from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.tools import SQL, Query

from ..tools import GPS_DRIFT_THRESHOLD_KM, GPS_MAX_GAP_SECONDS
from ..tools.geodesy import EARTH_RADIUS_KM


class DeviceDataLogGpsReport(models.Model):
    _name = "device.data.log.gps.report"
    _inherit = ["mixin.sql.report", "mixin.rolling.report"]
    _description = "GPS Observation Summary"
    _auto = False
    _rec_name = "date"
    _order = "date desc, device_id"

    _REPORT_TZ = "UTC"

    _rolling_key_field = "date"

    _rolling_window_days = 4

    device_id = fields.Many2one(
        comodel_name="device.device",
        readonly=True,
    )
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        readonly=True,
    )
    binding_id = fields.Many2one(
        comodel_name="resource.gps.binding",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    date = fields.Date(readonly=True)
    day_of_week = fields.Selection(
        selection=[
            ("0", "Sunday"),
            ("1", "Monday"),
            ("2", "Tuesday"),
            ("3", "Wednesday"),
            ("4", "Thursday"),
            ("5", "Friday"),
            ("6", "Saturday"),
        ],
        readonly=True,
    )
    week = fields.Char(
        readonly=True,
        help="ISO week number (YYYY-WNN)",
    )
    month = fields.Char(
        readonly=True,
        help="Month (YYYY-MM)",
    )

    log_count = fields.Integer(
        readonly=True,
        aggregator="sum",
        help="Number of GPS tracking points",
    )
    distance_best = fields.Float(
        digits=(12, 2),
        readonly=True,
        aggregator="sum",
        help="Best available distance (odometer if available, else GPS)",
    )
    distance_odo = fields.Float(
        digits=(12, 2),
        readonly=True,
        aggregator="sum",
        help="Distance derived from odometer delta (MAX - MIN). 0 if < 2 readings.",
    )
    distance_gps = fields.Float(
        digits=(12, 2),
        readonly=True,
        aggregator="sum",
        help="Distance calculated from GPS coordinates using Haversine formula",
    )
    distance_source = fields.Selection(
        selection=[
            ("odo", "Odometer"),
            ("gps", "GPS"),
        ],
        readonly=True,
        help="Which method was used for distance_best",
    )

    driving_hours = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="sum",
        help="Time with engine ON and vehicle moving",
    )
    idling_hours = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="sum",
        help="Time with engine ON but vehicle not moving (fuel waste indicator)",
    )
    parked_hours = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="sum",
        help="Time with engine OFF and vehicle not moving",
    )
    coasting_hours = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="sum",
        help="Time with engine OFF but vehicle moving (towing, rolling, or sensor error)",
    )
    tracked_hours = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="sum",
        help="Total time tracked (sum of all states)",
    )
    fuel_consumed_total = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="sum",
        help="Total fuel consumed",
    )
    fuel_refilled_total = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="sum",
        help="Total fuel added during refueling events",
    )
    engine_hours_total = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="sum",
        help="Total engine running time for the day",
    )

    speed_sum = fields.Float(
        digits=(14, 2),
        readonly=True,
        aggregator="sum",
        help="Sum of all speed readings (for weighted average)",
    )
    speed_count = fields.Integer(
        readonly=True,
        aggregator="sum",
        help="Count of speed readings (for weighted average)",
    )

    fuel_level_sum = fields.Float(
        digits=(14, 2),
        readonly=True,
        aggregator="sum",
    )
    fuel_level_count = fields.Integer(
        readonly=True,
        aggregator="sum",
    )

    engine_temp_sum = fields.Float(
        digits=(14, 2),
        readonly=True,
        aggregator="sum",
    )
    engine_temp_count = fields.Integer(
        readonly=True,
        aggregator="sum",
    )

    battery_voltage_sum = fields.Float(
        digits=(14, 3),
        readonly=True,
        aggregator="sum",
    )
    battery_voltage_count = fields.Integer(
        readonly=True,
        aggregator="sum",
    )

    quality_ok_sum = fields.Integer(
        readonly=True,
        aggregator="sum",
        help="Count of GPS readings with acceptable quality (HDOP <= 5, satellites >= 5)",
    )

    wheel_speed_sum = fields.Float(
        digits=(14, 2),
        readonly=True,
        aggregator="sum",
    )
    wheel_speed_count = fields.Integer(
        readonly=True,
        aggregator="sum",
    )
    speed_wheel_diff_sum = fields.Float(
        digits=(14, 2),
        readonly=True,
        aggregator="sum",
        help="Sum of absolute differences between GPS speed and wheel speed",
    )
    speed_wheel_diff_count = fields.Integer(
        readonly=True,
        aggregator="sum",
    )

    speed_max = fields.Float(
        digits=(10, 1),
        readonly=True,
        aggregator="max",
    )
    speed_min = fields.Float(
        digits=(10, 1),
        readonly=True,
        aggregator="min",
    )
    engine_temp_max = fields.Float(
        digits=(10, 1),
        readonly=True,
        aggregator="max",
    )
    battery_voltage_min = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="min",
    )
    external_voltage_min = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="min",
        help="Minimum external power supply voltage (detects power issues)",
    )
    engine_rpm_max = fields.Float(
        digits=(10, 0),
        readonly=True,
        aggregator="max",
        help="Maximum engine RPM (aggressive driving indicator)",
    )
    odometer_start = fields.Float(
        digits=(12, 2),
        readonly=True,
        aggregator="min",
    )
    odometer_end = fields.Float(
        digits=(12, 2),
        readonly=True,
        aggregator="max",
    )

    speed_over_warning_events = fields.Integer(
        readonly=True,
        aggregator="sum",
        help="Level 1: Readings exceeding warning threshold (config default: 80 km/h)",
    )
    speed_over_alert_events = fields.Integer(
        readonly=True,
        aggregator="sum",
        help="Level 2: Readings exceeding alert threshold (config default: 100 km/h)",
    )
    speed_over_critical_events = fields.Integer(
        readonly=True,
        aggregator="sum",
        help="Level 3: Readings exceeding critical threshold (config default: 120 km/h)",
    )
    ignition_on_count = fields.Integer(
        readonly=True,
        aggregator="sum",
        help="Count of readings with ignition on",
    )
    movement_count = fields.Integer(
        readonly=True,
        aggregator="sum",
        help="Count of readings where vehicle was moving",
    )

    speed_avg = fields.Float(
        digits=(10, 1),
        compute="_compute_ratios",
        help="Weighted average speed",
    )
    fuel_level_avg = fields.Float(
        digits=(10, 1),
        compute="_compute_ratios",
    )
    engine_temp_avg = fields.Float(
        digits=(10, 1),
        compute="_compute_ratios",
    )
    battery_voltage_avg = fields.Float(
        digits=(10, 2),
        compute="_compute_ratios",
    )
    quality_pct = fields.Float(
        digits=(5, 1),
        compute="_compute_ratios",
        help="Percentage of GPS readings with good quality",
    )
    wheel_speed_avg = fields.Float(
        digits=(10, 1),
        compute="_compute_ratios",
    )
    speed_wheel_discrepancy_avg = fields.Float(
        digits=(10, 1),
        compute="_compute_ratios",
        help="Average difference between GPS speed and wheel speed",
    )
    fuel_efficiency = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="avg",
        help="Kilometers per liter - higher is better. Aggregates correctly via _read_group_select.",
    )
    fuel_consumption = fields.Float(
        digits=(10, 2),
        readonly=True,
        aggregator="avg",
        help="Liters per 100 km - lower is better. Aggregates correctly via _read_group_select.",
    )
    utilization_pct = fields.Float(
        digits=(5, 1),
        compute="_compute_ratios",
        help="Percentage of GPS readings showing vehicle movement. Aggregates correctly across any time period.",
    )

    driving_pct = fields.Float(
        digits=(5, 1),
        readonly=True,
        aggregator="avg",
        help="Percentage of tracked time spent driving. Aggregates correctly via _read_group_select.",
    )
    idling_pct = fields.Float(
        digits=(5, 1),
        readonly=True,
        aggregator="avg",
        help="Percentage of tracked time spent idling. Aggregates correctly via _read_group_select.",
    )
    parked_pct = fields.Float(
        digits=(5, 1),
        readonly=True,
        aggregator="avg",
        help="Percentage of tracked time spent parked. Aggregates correctly via _read_group_select.",
    )
    coasting_pct = fields.Float(
        digits=(5, 1),
        readonly=True,
        aggregator="avg",
        help="Percentage of tracked time spent coasting. Aggregates correctly via _read_group_select.",
    )

    _RATIO_FIELDS = (
        ("speed_avg", "speed_sum", "speed_count", 1),
        ("fuel_level_avg", "fuel_level_sum", "fuel_level_count", 1),
        ("engine_temp_avg", "engine_temp_sum", "engine_temp_count", 1),
        ("battery_voltage_avg", "battery_voltage_sum", "battery_voltage_count", 1),
        ("wheel_speed_avg", "wheel_speed_sum", "wheel_speed_count", 1),
        (
            "speed_wheel_discrepancy_avg",
            "speed_wheel_diff_sum",
            "speed_wheel_diff_count",
            1,
        ),
        ("quality_pct", "quality_ok_sum", "log_count", 100),
        ("utilization_pct", "movement_count", "log_count", 100),
    )

    @api.depends(
        "speed_sum",
        "speed_count",
        "fuel_level_sum",
        "fuel_level_count",
        "engine_temp_sum",
        "engine_temp_count",
        "battery_voltage_sum",
        "battery_voltage_count",
        "wheel_speed_sum",
        "wheel_speed_count",
        "speed_wheel_diff_sum",
        "speed_wheel_diff_count",
        "quality_ok_sum",
        "movement_count",
        "log_count",
    )
    def _compute_ratios(self) -> None:
        for rec in self:
            for target, numerator, denominator, scale in self._RATIO_FIELDS:
                divisor = rec[denominator]
                rec[target] = (rec[numerator] / divisor) * scale if divisor else 0

    def _report_tz_sql(self) -> SQL:
        return SQL("%s", self._REPORT_TZ)

    def _local_day_expression(self) -> str:
        return "log.timestamp AT TIME ZONE 'UTC' AT TIME ZONE log.resource_tz"

    def _rolling_cutoff_date(self):
        tz = ZoneInfo(self._REPORT_TZ)
        local_now = fields.Datetime.now().replace(tzinfo=UTC).astimezone(tz)
        return local_now.date() - timedelta(days=self._rolling_window_days + 1)

    def _rolling_cutoff_sql(self) -> SQL:
        return SQL("%s::date", self._rolling_cutoff_date())

    def _rolling_cutoff_utc_sql(self) -> SQL:
        local_midnight = datetime.combine(
            self._rolling_cutoff_date() - timedelta(days=1),
            time(),
            tzinfo=ZoneInfo(self._REPORT_TZ),
        )
        return SQL("%s::timestamp", local_midnight.astimezone(UTC).replace(tzinfo=None))

    def _rolling_scope(self) -> SQL:
        cutoff = self._rolling_cutoff_utc_sql()
        self.env.cr.execute(
            SQL(
                """
                SELECT d.id, COALESCE(seed.ts, %(cutoff)s)
                  FROM device_device d
                  LEFT JOIN (
                        SELECT device_id, max(timestamp) AS ts
                          FROM device_data_log_gps
                         WHERE timestamp < %(cutoff)s
                         GROUP BY device_id
                       ) seed ON seed.device_id = d.id
                """,
                cutoff=cutoff,
            )
        )
        floors = self.env.cr.fetchall()
        if not floors:
            return SQL("(SELECT src.* FROM device_data_log_gps src WHERE false) log")
        ranges = SQL(" OR ").join(
            SQL("(src.device_id = %s AND src.timestamp >= %s)", device_id, floor)
            for device_id, floor in floors
        )
        return SQL("(SELECT src.* FROM device_data_log_gps src WHERE %s) log", ranges)

    def _read_group_select(self, aggregate_spec: str, query: Query) -> SQL:
        if aggregate_spec == "fuel_efficiency:avg":
            return SQL(
                "SUM(%(f_dist)s) / NULLIF(SUM(%(f_fuel)s), 0)",
                f_dist=self._field_to_sql(self._table, "distance_best", query),
                f_fuel=self._field_to_sql(self._table, "fuel_consumed_total", query),
            )
        if aggregate_spec == "fuel_consumption:avg":
            return SQL(
                "(SUM(%(f_fuel)s) * 100) / NULLIF(SUM(%(f_dist)s), 0)",
                f_fuel=self._field_to_sql(self._table, "fuel_consumed_total", query),
                f_dist=self._field_to_sql(self._table, "distance_best", query),
            )
        state_pct_fields = {
            "driving_pct:avg": "driving_hours",
            "idling_pct:avg": "idling_hours",
            "parked_pct:avg": "parked_hours",
            "coasting_pct:avg": "coasting_hours",
        }
        if aggregate_spec in state_pct_fields:
            return SQL(
                "(SUM(%(f_state)s) / NULLIF(SUM(%(f_total)s), 0)) * 100",
                f_state=self._field_to_sql(
                    self._table, state_pct_fields[aggregate_spec], query
                ),
                f_total=self._field_to_sql(self._table, "tracked_hours", query),
            )
        return super()._read_group_select(aggregate_spec, query)

    _GPS_DRIFT_THRESHOLD_KM = GPS_DRIFT_THRESHOLD_KM

    _GPS_MAX_GAP_SECONDS = GPS_MAX_GAP_SECONDS

    def _with_cte(self) -> SQL:
        return SQL(
            """
            gps_with_computed AS (
                SELECT
                    log.id,
                    log.device_id,
                    COALESCE(binding.company_id, dev.company_id) AS company_id,
                    binding.resource_id, binding.binding_id,
                    COALESCE(binding.tz, device_clock.tz) AS resource_tz,
                    log.timestamp,
                    log.latitude,
                    log.longitude,
                    log.real_odometer,
                    log.odometer_valid,
                    log.fuel_consumed,
                    log.fuel_refilled,
                    log.fuel_level,
                    log.fuel_level_l,
                    log.speed,
                    log.wheel_speed,
                    log.movement,
                    log.ignition,
                    log.engine_temperature,
                    log.engine_hours,
                    log.engine_total_hours,
                    log.engine_speed_rpm,
                    log.battery_voltage,
                    log.external_voltage,
                    log.gnss_hdop,
                    log.satellites,
                    -- Previous coordinates via LAG window function
                    LAG(log.latitude) OVER (
                        PARTITION BY log.device_id, binding.binding_id
                        ORDER BY log.timestamp, log.id
                    ) AS prev_latitude,
                    LAG(log.longitude) OVER (
                        PARTITION BY log.device_id, binding.binding_id
                        ORDER BY log.timestamp, log.id
                    ) AS prev_longitude,
                    -- Previous timestamp for time delta calculation
                    LAG(log.timestamp) OVER (
                        PARTITION BY log.device_id, binding.binding_id
                        ORDER BY log.timestamp, log.id
                    ) AS prev_timestamp,
                    -- Previous engine hours for delta calculation
                    LAG(log.engine_total_hours) OVER (
                        PARTITION BY log.device_id, binding.binding_id
                        ORDER BY log.timestamp, log.id
                    ) AS prev_engine_hours,
                    -- Haversine distance calculation (returns km)
                    CASE
                        WHEN LAG(log.latitude) OVER (
                            PARTITION BY log.device_id, binding.binding_id ORDER BY log.timestamp, log.id
                        ) IS NOT NULL
                        AND LAG(log.longitude) OVER (
                            PARTITION BY log.device_id, binding.binding_id ORDER BY log.timestamp, log.id
                        ) IS NOT NULL
                        THEN
                            2 * %(earth_radius_km)s * ASIN(
                                SQRT(
                                    POWER(SIN(RADIANS(
                                        log.latitude - LAG(log.latitude) OVER (
                                            PARTITION BY log.device_id, binding.binding_id ORDER BY log.timestamp, log.id
                                        )
                                    ) / 2), 2)
                                    + COS(RADIANS(LAG(log.latitude) OVER (
                                        PARTITION BY log.device_id, binding.binding_id ORDER BY log.timestamp, log.id
                                    )))
                                    * COS(RADIANS(log.latitude))
                                    * POWER(SIN(RADIANS(
                                        log.longitude - LAG(log.longitude) OVER (
                                            PARTITION BY log.device_id, binding.binding_id ORDER BY log.timestamp, log.id
                                        )
                                    ) / 2), 2)
                                )
                            )
                        ELSE 0
                    END AS gps_distance_km,
                    -- GPS quality indicator (1 = acceptable, 0 = poor)
                    -- HDOP <= 5 is industry standard for acceptable accuracy
                    -- Satellites >= 5 ensures adequate triangulation
                    -- Note: Teltonika devices use gnss_hdop field
                    CASE
                        WHEN COALESCE(log.gnss_hdop, 99) <= 5
                             AND COALESCE(log.satellites, 0) >= 5
                        THEN 1
                        ELSE 0
                    END AS quality_ok,
                    -- Speed vs wheel speed discrepancy (absolute difference)
                    CASE
                        WHEN log.speed IS NOT NULL AND log.wheel_speed IS NOT NULL
                        THEN ABS(log.speed - log.wheel_speed)
                        ELSE NULL
                    END AS speed_wheel_diff,
                    -- Is vehicle moving? (movement flag OR speed > 0)
                    CASE
                        WHEN log.movement = TRUE OR COALESCE(log.speed, 0) > 0
                        THEN TRUE
                        ELSE FALSE
                    END AS is_moving,
                    -- 3-Level Speed Limits from config (with defaults)
                    COALESCE(cfg.speed_limit_warning, 80.0) AS speed_limit_warning,
                    COALESCE(cfg.speed_limit_alert, 100.0) AS speed_limit_alert,
                    COALESCE(cfg.speed_limit_critical, 120.0) AS speed_limit_critical
                FROM %(source)s
                LEFT JOIN device_device dev ON dev.id = log.device_id
                LEFT JOIN (%(device_timezones)s) device_clock ON device_clock.device_id = log.device_id
                LEFT JOIN LATERAL (%(binding_query)s) binding ON TRUE
                LEFT JOIN device_profile cfg ON cfg.id = dev.config_id
            ),
            -- Second CTE: Apply threshold filter and compute derived values
            gps_filtered AS (
                SELECT
                    *,
                    -- Only count distance if above threshold (filters GPS drift)
                    CASE
                        WHEN gps_distance_km >= %(threshold)s THEN gps_distance_km
                        ELSE 0
                    END AS filtered_distance_km,
                    -- Engine hours delta (positive only, handles counter resets).
                    -- Reads engine_total_hours, the column the ingest pipeline
                    -- writes (Teltonika code 102). This lagged
                    -- engine_total_hours but subtracted engine_hours, a
                    -- different column that no producer ever writes outside the
                    -- demo data — so the guard never passed and
                    -- engine_hours_total was permanently 0 for real fleets. A
                    -- device logging 4.9 h of engine time reported 0.0.
                    CASE
                        WHEN engine_total_hours IS NOT NULL
                             AND prev_engine_hours IS NOT NULL
                             AND engine_total_hours >= prev_engine_hours
                        THEN engine_total_hours - prev_engine_hours
                        ELSE 0
                    END AS engine_hours_delta,
                    -- Time delta in seconds, capped at the shared gap limit:
                    -- larger gaps are likely signal loss, not state duration
                    CASE
                        WHEN prev_timestamp IS NOT NULL
                        THEN LEAST(
                            EXTRACT(EPOCH FROM (timestamp - prev_timestamp)),
                            %(max_gap)s
                        )
                        ELSE NULL
                    END AS time_delta_seconds,
                    -- Vehicle state: driving, idling, parked, coasting
                    -- With NULL ignition fallback to movement-only
                    CASE
                        -- Ignition known: ON
                        WHEN ignition = TRUE AND is_moving THEN 'driving'
                        WHEN ignition = TRUE AND NOT is_moving THEN 'idling'
                        -- Ignition known: OFF
                        WHEN ignition = FALSE AND is_moving THEN 'coasting'
                        WHEN ignition = FALSE AND NOT is_moving THEN 'parked'
                        -- Ignition NULL: fallback to movement
                        WHEN ignition IS NULL AND is_moving THEN 'driving'
                        WHEN ignition IS NULL AND NOT is_moving THEN 'parked'
                        ELSE 'unknown'
                    END AS vehicle_state
                FROM gps_with_computed
            )
            """,
            binding_query=self.env["resource.gps.binding"]._at_query(
                SQL("log.device_id"), SQL("log.timestamp")
            ),
            device_timezones=self.env["device.device"]._gps_timezone_query(),
            source=self._rolling_source_sql(),
            threshold=self._GPS_DRIFT_THRESHOLD_KM,
            max_gap=self._GPS_MAX_GAP_SECONDS,
            earth_radius_km=EARTH_RADIUS_KM,
        )

    def _rolling_source_sql(self) -> SQL:
        return self._rolling_scope_sql() or SQL("device_data_log_gps log")

    _FUEL_CONSUMED_SQL = """
        CASE
            WHEN COUNT(NULLIF(log.fuel_level_l, 0)) >= 2 THEN
                GREATEST(
                    (array_agg(log.fuel_level_l ORDER BY log.timestamp ASC)
                        FILTER (WHERE log.fuel_level_l > 0))[1]
                    -
                    (array_agg(log.fuel_level_l ORDER BY log.timestamp DESC)
                        FILTER (WHERE log.fuel_level_l > 0))[1]
                    +
                    COALESCE(SUM(log.fuel_refilled), 0),
                    0
                )
            ELSE 0
        END
    """

    _DISTANCE_BEST_SQL = """
        CASE
            WHEN COUNT(NULLIF(log.real_odometer, 0))
                 FILTER (WHERE log.odometer_valid = TRUE) >= 2 THEN
                COALESCE(
                    MAX(log.real_odometer) FILTER (WHERE log.odometer_valid = TRUE)
                    - MIN(NULLIF(log.real_odometer, 0))
                      FILTER (WHERE log.odometer_valid = TRUE),
                    0
                )
            ELSE COALESCE(SUM(log.filtered_distance_km), 0)
        END
    """

    def _get_fields_select(self) -> dict:
        fuel_consumed = self._FUEL_CONSUMED_SQL
        distance_best = self._DISTANCE_BEST_SQL
        local_ts = self._local_day_expression()
        return {
            "id": "MIN(log.id)",
            "device_id": "log.device_id",
            "resource_id": "log.resource_id",
            "binding_id": "log.binding_id",
            "company_id": "log.company_id",
            "date": f"DATE({local_ts})",
            "day_of_week": f"EXTRACT(DOW FROM {local_ts})::text",
            "week": f"TO_CHAR({local_ts}, 'IYYY-\"W\"IW')",
            "month": f"TO_CHAR({local_ts}, 'YYYY-MM')",
            "log_count": "COUNT(*)",
            "driving_hours": """
                COALESCE(SUM(log.time_delta_seconds)
                    FILTER (WHERE log.vehicle_state = 'driving'), 0) / 3600.0
            """,
            "idling_hours": """
                COALESCE(SUM(log.time_delta_seconds)
                    FILTER (WHERE log.vehicle_state = 'idling'), 0) / 3600.0
            """,
            "parked_hours": """
                COALESCE(SUM(log.time_delta_seconds)
                    FILTER (WHERE log.vehicle_state = 'parked'), 0) / 3600.0
            """,
            "coasting_hours": """
                COALESCE(SUM(log.time_delta_seconds)
                    FILTER (WHERE log.vehicle_state = 'coasting'), 0) / 3600.0
            """,
            "tracked_hours": """
                COALESCE(SUM(log.time_delta_seconds), 0) / 3600.0
            """,
            "driving_pct": """
                CASE
                    WHEN COALESCE(SUM(log.time_delta_seconds), 0) > 0 THEN
                        (COALESCE(SUM(log.time_delta_seconds)
                            FILTER (WHERE log.vehicle_state = 'driving'), 0)
                        / SUM(log.time_delta_seconds)) * 100
                    ELSE 0
                END
            """,
            "idling_pct": """
                CASE
                    WHEN COALESCE(SUM(log.time_delta_seconds), 0) > 0 THEN
                        (COALESCE(SUM(log.time_delta_seconds)
                            FILTER (WHERE log.vehicle_state = 'idling'), 0)
                        / SUM(log.time_delta_seconds)) * 100
                    ELSE 0
                END
            """,
            "parked_pct": """
                CASE
                    WHEN COALESCE(SUM(log.time_delta_seconds), 0) > 0 THEN
                        (COALESCE(SUM(log.time_delta_seconds)
                            FILTER (WHERE log.vehicle_state = 'parked'), 0)
                        / SUM(log.time_delta_seconds)) * 100
                    ELSE 0
                END
            """,
            "coasting_pct": """
                CASE
                    WHEN COALESCE(SUM(log.time_delta_seconds), 0) > 0 THEN
                        (COALESCE(SUM(log.time_delta_seconds)
                            FILTER (WHERE log.vehicle_state = 'coasting'), 0)
                        / SUM(log.time_delta_seconds)) * 100
                    ELSE 0
                END
            """,
            "distance_odo": """
                CASE
                    WHEN COUNT(NULLIF(log.real_odometer, 0))
                         FILTER (WHERE log.odometer_valid = TRUE) >= 2 THEN
                        COALESCE(
                            MAX(log.real_odometer) FILTER (WHERE log.odometer_valid = TRUE)
                            - MIN(NULLIF(log.real_odometer, 0))
                              FILTER (WHERE log.odometer_valid = TRUE),
                            0
                        )
                    ELSE 0
                END
            """,
            "distance_gps": "COALESCE(SUM(log.filtered_distance_km), 0)",
            "distance_best": distance_best,
            "distance_source": """
                CASE
                    WHEN COUNT(NULLIF(log.real_odometer, 0))
                         FILTER (WHERE log.odometer_valid = TRUE) >= 2 THEN 'odo'
                    ELSE 'gps'
                END
            """,
            "odometer_start": """
                MIN(NULLIF(log.real_odometer, 0))
                FILTER (WHERE log.odometer_valid = TRUE)
            """,
            "odometer_end": """
                MAX(log.real_odometer)
                FILTER (WHERE log.odometer_valid = TRUE)
            """,
            "fuel_consumed_total": fuel_consumed,
            "fuel_refilled_total": "COALESCE(SUM(log.fuel_refilled), 0)",
            "fuel_level_sum": "COALESCE(SUM(NULLIF(log.fuel_level, 0)), 0)",
            "fuel_level_count": "COUNT(NULLIF(log.fuel_level, 0))",
            "fuel_efficiency": f"""
                CASE
                    WHEN ({fuel_consumed}) > 0 THEN
                        ({distance_best}) / NULLIF(({fuel_consumed}), 0)
                    ELSE 0
                END
            """,
            "fuel_consumption": f"""
                CASE
                    WHEN ({distance_best}) > 0 THEN
                        (({fuel_consumed}) * 100) / NULLIF(({distance_best}), 0)
                    ELSE 0
                END
            """,
            "speed_sum": "COALESCE(SUM(NULLIF(log.speed, 0)), 0)",
            "speed_count": "COUNT(NULLIF(log.speed, 0))",
            "speed_max": "MAX(log.speed)",
            "speed_min": "MIN(NULLIF(log.speed, 0))",
            "speed_over_warning_events": """
                COUNT(*) FILTER (WHERE log.speed > log.speed_limit_warning)
            """,
            "speed_over_alert_events": """
                COUNT(*) FILTER (WHERE log.speed > log.speed_limit_alert)
            """,
            "speed_over_critical_events": """
                COUNT(*) FILTER (WHERE log.speed > log.speed_limit_critical)
            """,
            "movement_count": """
                COUNT(*) FILTER (WHERE log.movement = TRUE OR log.speed > 0)
            """,
            "ignition_on_count": "COUNT(*) FILTER (WHERE log.ignition = TRUE)",
            "engine_temp_sum": "COALESCE(SUM(NULLIF(log.engine_temperature, 0)), 0)",
            "engine_temp_count": "COUNT(NULLIF(log.engine_temperature, 0))",
            "engine_temp_max": "MAX(log.engine_temperature)",
            "engine_hours_total": "COALESCE(SUM(log.engine_hours_delta), 0)",
            "engine_rpm_max": "MAX(log.engine_speed_rpm)",
            "battery_voltage_sum": "COALESCE(SUM(NULLIF(log.battery_voltage, 0)), 0)",
            "battery_voltage_count": "COUNT(NULLIF(log.battery_voltage, 0))",
            "battery_voltage_min": "MIN(NULLIF(log.battery_voltage, 0))",
            "external_voltage_min": "MIN(NULLIF(log.external_voltage, 0))",
            "quality_ok_sum": "COALESCE(SUM(log.quality_ok), 0)",
            "wheel_speed_sum": "COALESCE(SUM(NULLIF(log.wheel_speed, 0)), 0)",
            "wheel_speed_count": "COUNT(NULLIF(log.wheel_speed, 0))",
            "speed_wheel_diff_sum": "COALESCE(SUM(log.speed_wheel_diff), 0)",
            "speed_wheel_diff_count": "COUNT(log.speed_wheel_diff)",
        }

    def _get_from_tables(self) -> list:
        return [
            ("gps_filtered", "log", None, None),
        ]

    def _get_where_conditions(self) -> list:
        return []

    def _get_fields_group_by(self) -> list:
        local_ts = self._local_day_expression()
        return [
            "log.device_id",
            "log.resource_id",
            "log.binding_id",
            "log.company_id",
            f"DATE({local_ts})",
            f"EXTRACT(DOW FROM {local_ts})",
            f"TO_CHAR({local_ts}, 'IYYY-\"W\"IW')",
            f"TO_CHAR({local_ts}, 'YYYY-MM')",
        ]

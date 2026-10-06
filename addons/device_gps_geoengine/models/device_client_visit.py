import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .device_device import CLIENT_PROXIMITY_TOLERANCE_M, VISIT_MAX_SILENCE

_logger = logging.getLogger(__name__)


class DeviceClientVisit(models.Model):
    _name = "device.client.visit"
    _description = "GPS Visit to a Client Parcel"
    _order = "arrival desc"

    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="device_id.company_id",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Client",
        index=True,
        required=True,
    )
    geofence_id = fields.Many2one(
        comodel_name="device.geo.fence",
        string="Parcel",
        required=True,
    )
    arrival = fields.Datetime(
        index=True,
        required=True,
    )
    departure = fields.Datetime(help="Empty while the visit is still ongoing.")
    duration_hours = fields.Float(
        string="Duration (h)",
        compute="_compute_duration_hours",
        aggregator=None,
        help="Elapsed time so far while the visit is ongoing (recomputed "
        "on every read, not stored, so it stays current without needing "
        "the cron to touch the row); the final arrival-to-departure span "
        "once it has ended. Not stored, so it cannot be summed by "
        "group-by (aggregator=None) -- grouping crashed on that before "
        "this was added.",
    )

    @api.depends("arrival", "departure")
    def _compute_duration_hours(self) -> None:
        now = fields.Datetime.now()
        for visit in self:
            if not visit.arrival:
                visit.duration_hours = 0.0
                continue
            end = visit.departure or now
            visit.duration_hours = (end - visit.arrival).total_seconds() / 3600.0

    @api.model
    def _rebuild_from_gps_logs(self, device_ids, date_from, date_to) -> int:
        """Rebuild the client visits of `device_ids` between two UTC
        datetimes from the raw GPS positions.

        The 5-minute cron only records visits while it is running, so the
        history before the module was installed -- or across any outage --
        is empty. This replays the positions through the same proximity
        rule as the live tracker and sessionizes them: consecutive
        positions on the same parcel are one visit, and a silence shorter
        than VISIT_MAX_SILENCE does not end it (the tracker sleeps
        while parked).

        Existing visits of those devices that start inside the window are
        replaced; ongoing visits (no departure) are left alone so the live
        tracker keeps owning them. Returns the number of visits created.
        """
        self.check_access("create")
        self.check_access("unlink")
        devices = self.env["device.device"].browse(sorted(set(device_ids)))
        devices.check_access("read")
        self.env["device.data.log.gps"].check_access("read")
        device_ids = devices.ids
        if not device_ids:
            return 0
        if date_from >= date_to:
            raise ValidationError(
                self.env._("The replay window must have a positive duration.")
            )
        fences = self.env["device.geo.fence"].search(
            [
                ("active", "=", True),
                ("area_type", "=", "parcel"),
                ("partner_id", "!=", False),
            ]
        )
        self.flush_model()
        self.env["device.data.log.gps"].flush_model(
            ["device_id", "timestamp", "latitude", "longitude"]
        )
        self.env["device.geo.fence"].flush_model(
            ["active", "area_type", "partner_id", "the_geom", "company_id"]
        )
        cr = self.env.cr
        cr.execute(
            """
            DELETE FROM device_client_visit
             WHERE device_id = ANY(%s)
               AND arrival >= %s AND arrival < %s
               AND departure IS NOT NULL
            """,
            (device_ids, date_from, date_to),
        )
        deleted = cr.rowcount
        cr.execute(
            """
            WITH positioned AS (
                SELECT l.id, l.device_id, l.timestamp,
                       f.id AS geofence_id, f.partner_id
                  FROM device_data_log_gps l
                  JOIN device_device d ON d.id = l.device_id
                  LEFT JOIN LATERAL (
                        SELECT f.id, f.partner_id
                          FROM device_geo_fence f
                         WHERE f.id = ANY(%(fence_ids)s) AND f.area_type = 'parcel'
                           AND (f.company_id IS NULL OR f.company_id = d.company_id)
                           AND f.active
                           AND f.partner_id IS NOT NULL
                           AND ST_DWithin(
                                 f.the_geom,
                                 ST_Transform(ST_SetSRID(
                                     ST_MakePoint(l.longitude, l.latitude), 4326
                                 ), 3857),
                                 -- Web Mercator inflates distances by
                                 -- 1/cos(latitude); see device.device.
                                 %(tolerance)s / cosd(l.latitude))
                         ORDER BY ST_Distance(
                                 f.the_geom,
                                 ST_Transform(ST_SetSRID(
                                     ST_MakePoint(l.longitude, l.latitude), 4326
                                 ), 3857))
                         LIMIT 1
                       ) f ON TRUE
                 WHERE l.device_id = ANY(%(device_ids)s)
                   AND l.timestamp >= %(date_from)s
                   AND l.timestamp < %(date_to)s
                   AND l.latitude BETWEEN -89.999999 AND 89.999999
                   AND l.longitude BETWEEN -180 AND 180
                   AND NOT (l.latitude = 0 AND l.longitude = 0)
            ),
            marked AS (
                SELECT *,
                       CASE
                           WHEN geofence_id IS DISTINCT FROM LAG(geofence_id) OVER w
                             OR timestamp - LAG(timestamp) OVER w
                                > %(max_silence)s::interval
                           THEN 1 ELSE 0
                       END AS starts_group
                  FROM positioned
                WINDOW w AS (PARTITION BY device_id ORDER BY timestamp, id)
            ),
            grouped AS (
                SELECT *,
                       SUM(starts_group) OVER (
                           PARTITION BY device_id ORDER BY timestamp, id
                       ) AS group_no
                  FROM marked
            ),
            visits AS (
                SELECT device_id, geofence_id, partner_id,
                       MIN(timestamp) AS arrival,
                       MAX(timestamp) AS departure
                  FROM grouped
                 WHERE geofence_id IS NOT NULL
                 GROUP BY device_id, group_no, geofence_id, partner_id
            )
            INSERT INTO device_client_visit
                (device_id, geofence_id, partner_id, arrival, departure,
                 create_uid, create_date, write_uid, write_date)
            SELECT v.device_id, v.geofence_id, v.partner_id,
                   v.arrival, v.departure,
                   %(uid)s, now() AT TIME ZONE 'UTC',
                   %(uid)s, now() AT TIME ZONE 'UTC'
              FROM visits v
             WHERE NOT EXISTS (
                   SELECT 1 FROM device_client_visit o
                    WHERE o.device_id = v.device_id
                      AND o.departure IS NULL
                      AND o.arrival <= v.arrival
             )
            RETURNING id
            """,
            {
                "tolerance": CLIENT_PROXIMITY_TOLERANCE_M,
                "device_ids": device_ids,
                "fence_ids": fences.ids,
                "date_from": date_from,
                "date_to": date_to,
                "max_silence": VISIT_MAX_SILENCE,
                "uid": self.env.uid,
            },
        )
        created = self.browse([row[0] for row in cr.fetchall()])
        self.invalidate_model()
        # The raw insert bypassed the ORM: recompute every stored computed
        # or related field (company_id, operator snapshots, ...) so the rows
        # look exactly like ones the live tracker would have created.
        for field in self._fields.values():
            if field.store and field.compute:
                self.env.add_to_compute(field, created)
        created.flush_recordset()
        _logger.info(
            "Rebuilt client visits for %d device(s) between %s and %s: "
            "%d removed, %d created",
            len(device_ids),
            date_from,
            date_to,
            deleted,
            len(created),
        )
        return len(created)

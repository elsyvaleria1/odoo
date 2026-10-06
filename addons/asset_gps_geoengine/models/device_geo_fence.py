from odoo import fields, models
from odoo.tools import SQL

from .device_gps_stop import LONG_PARK_MINUTES


class DeviceGeoFence(models.Model):
    _inherit = "device.geo.fence"

    to_mark = fields.Boolean(
        string="To Mark",
        compute="_compute_to_mark",
        search="_search_to_mark",
        help=f"A vehicle stayed here more than {LONG_PARK_MINUTES} minutes and "
        "the geofence has no client. Stays set, as a signal to mark it, until "
        "it gets a client or is made internal.",
    )

    def _to_mark_ids(self):
        """Geofences without a client, not internal, under a stop that is
        still a place to mark (device.gps.stop.to_mark)."""
        stops = self.env["device.gps.stop"]
        stops._flush_to_mark_inputs()
        self.env.cr.execute(
            SQL(
                """
                SELECT DISTINCT s.geofence_id
                  FROM device_gps_stop s
                  JOIN device_geo_fence f ON f.id = s.geofence_id
                 WHERE f.active AND f.partner_id IS NULL
                   AND f.usage IS DISTINCT FROM 'internal'
                   AND %s
                """,
                stops._to_mark_sql("s"),
            )
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def _compute_to_mark(self):
        pending = set(self._to_mark_ids())
        for geofence in self:
            geofence.to_mark = geofence.id in pending

    def _search_to_mark(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        positive = (operator == "in") == (True in value)
        return [("id", "in" if positive else "not in", self._to_mark_ids())]

import logging

from odoo import api, fields, models

from odoo.addons.device.tools import fdw
from odoo.addons.geoengine.models.fields import GeoField, geo_index_name

_logger = logging.getLogger(__name__)


class DeviceDataLogGps(models.Model):
    _inherit = "device.data.log.gps"

    the_point = fields.GeoPoint(
        compute="_compute_the_point",
        store=True,
        srid=4326,
        help="Geographic point for map display (WGS84/EPSG:4326)",
    )

    @api.depends("latitude", "longitude")
    def _compute_the_point(self) -> None:
        for record in self:
            if record.latitude or record.longitude:
                record.the_point = f"POINT({record.longitude} {record.latitude})"
            else:
                record.the_point = False

    def _auto_init(self):
        result = super()._auto_init()
        self._create_remote_geo_indexes()
        return result

    # A foreign table's spatial index lives on its remote table, which neither
    # the FDW schema sync nor geoengine creates; without it every map tile
    # scans the GPS log. Built concurrently so GPS ingestion is not blocked.
    def _create_remote_geo_indexes(self) -> None:
        cr = self.env.cr
        if not fdw.is_foreign(cr, self._table) or not fdw.dblink_available(cr):
            return
        server = fdw.foreign_server(cr, self._table)
        target = fdw.remote_table(cr, self._table)
        for field in self._fields.values():
            if not isinstance(field, GeoField) or not field.store:
                continue
            name = geo_index_name(self._table, field.name)
            if fdw.remote_index_exists(cr, server, name):
                continue
            _logger.info(
                "FDW %s: creating spatial index %s on %s", server, name, target
            )
            fdw.remote_exec(
                cr,
                server,
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                f"ON {target} USING gist ({field.name})",
            )

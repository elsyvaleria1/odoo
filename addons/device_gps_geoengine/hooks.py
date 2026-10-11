import logging

from odoo.addons.device.tools import fdw

_logger = logging.getLogger(__name__)


def post_init_hook(env) -> None:
    _logger.info("Computing the_point for existing GPS log records...")

    env.cr.execute("""
        SELECT srid FROM geometry_columns
        WHERE f_table_name = 'device_data_log_gps' AND f_geometry_column = 'the_point'
    """)
    result = env.cr.fetchone()

    foreign = fdw.is_foreign(env.cr, "device_data_log_gps")
    if result and result[0] != 4326 and not foreign:
        _logger.info("Converting the_point column from SRID %s to 4326", result[0])
        env.cr.execute(
            "ALTER TABLE device_data_log_gps DROP COLUMN IF EXISTS the_point"
        )
        env.cr.execute(
            "SELECT AddGeometryColumn('device_data_log_gps', 'the_point', 4326, 'POINT', 2)"
        )
        env.cr.execute("""
            CREATE INDEX IF NOT EXISTS device_data_log_gps_the_point_gist_idx
            ON device_data_log_gps USING GIST (the_point)
            """)

    env.cr.execute("""
        UPDATE device_data_log_gps
        SET the_point = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        WHERE the_point IS NULL
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
          AND NOT (latitude = 0 AND longitude = 0)
    """)
    _logger.info("Updated %d GPS log records with the_point", env.cr.rowcount)

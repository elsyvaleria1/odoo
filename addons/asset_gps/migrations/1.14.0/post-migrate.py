from odoo import SUPERUSER_ID, api
from odoo.db import schema

# where resource_asset 2.0 keeps what the asset tree held beside its resource
LEGACY = "resource_asset_legacy"


def migrate(cr, version):
    if not version or not schema.column_exists(cr, LEGACY, "gps_device_id"):
        return
    # A direct SQL transfer must enforce the new relation's company invariant.
    cr.execute("""
        SELECT a.id
          FROM resource_asset_legacy a
          JOIN resource_resource r ON r.id = a.id
          JOIN device_device d ON d.id = a.gps_device_id
         WHERE d.company_id IS NOT NULL
           AND r.company_id IS DISTINCT FROM d.company_id
         LIMIT 1
    """)
    if cr.fetchone():
        raise ValueError("GPS migration: tracker and resource companies disagree")
    # SELECT through the inheritance root includes every concrete asset kind.
    # Refuse ambiguity before changing either side of the identity.
    cr.execute("""
        SELECT a.id
          FROM resource_asset_legacy a
          JOIN resource_resource r ON r.id = a.id
         WHERE a.gps_device_id IS NOT NULL
           AND r.gps_device_id IS NOT NULL
           AND a.gps_device_id != r.gps_device_id
         LIMIT 1
    """)
    if cr.fetchone():
        raise ValueError(
            "GPS migration: asset and resource tracking attachments disagree"
        )
    cr.execute("""
        SELECT gps_device_id
          FROM (
                SELECT id AS resource_id, gps_device_id FROM resource_asset_legacy
                 WHERE gps_device_id IS NOT NULL
                UNION
                SELECT id, gps_device_id FROM resource_resource
                 WHERE gps_device_id IS NOT NULL
               ) attachments
         GROUP BY gps_device_id
        HAVING count(DISTINCT resource_id) > 1
         LIMIT 1
    """)
    if cr.fetchone():
        raise ValueError("GPS migration: a device is attached to several resources")
    cr.execute("""
        UPDATE resource_resource r
           SET gps_device_id = a.gps_device_id
          FROM resource_asset_legacy a
         WHERE r.id = a.id
           AND a.gps_device_id IS NOT NULL
           AND r.gps_device_id IS NULL
    """)
    # resource_asset 2.0 held the column for this migration, which takes it
    schema.drop_columns(cr, LEGACY, ["gps_device_id"])
    # SQL transfer bypasses attachment write hooks. Rebuild settled local dates.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["resource.gps.binding"]._bootstrap_legacy()
    env["device.data.log.gps.report"]._rolling_mark_stale()

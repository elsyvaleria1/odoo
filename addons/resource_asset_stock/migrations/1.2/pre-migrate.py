import logging

from odoo.db.schema import column_exists, drop_columns, drop_index

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    drop_index(cr, "resource_resource__trace_id_index", "resource_resource")
    if not column_exists(cr, "product_trace", "asset_id"):
        return
    cr.execute(
        """
        UPDATE resource_resource asset
           SET trace_id = lot.id
          FROM product_trace lot
         WHERE lot.asset_id = asset.id
           AND asset.trace_id IS NULL
           AND NOT EXISTS (
                   SELECT 1 FROM resource_resource other WHERE other.trace_id = lot.id
               )
        """
    )
    if cr.rowcount:
        _logger.info("%s assets took their serial from the lot's link.", cr.rowcount)
    cr.execute(
        """
        WITH ranked AS (
            SELECT asset.id,
                   row_number() OVER (
                       PARTITION BY asset.trace_id
                       ORDER BY (lot.asset_id = asset.id) DESC NULLS LAST, asset.id
                   ) AS rank
              FROM resource_resource asset
              JOIN product_trace lot ON lot.id = asset.trace_id
        )
        UPDATE resource_resource asset
           SET trace_id = NULL
          FROM ranked
         WHERE ranked.id = asset.id AND ranked.rank > 1
     RETURNING asset.id
        """
    )
    if released := [row[0] for row in cr.fetchall()]:
        _logger.warning(
            "Assets %s shared a serial with another asset and lost it.", released
        )
    drop_columns(cr, "product_trace", ["asset_id"])

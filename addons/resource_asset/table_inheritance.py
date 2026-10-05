import logging

from odoo.db.schema import column_exists, rename_column, table_exists
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


def set_aside_root_columns(cr, columns) -> None:
    """Rename the root's copy of each column to `legacy_<name>` before the
    schema pass, so that a subtype gets a column of its own instead of
    inheriting the root's. The values wait in the set-aside column for the
    post-migration that reads them."""
    if not table_exists(cr, "resource_asset"):
        return
    for column in columns:
        if column_exists(cr, "resource_asset", column):
            rename_column(cr, "resource_asset", column, f"legacy_{column}")


def _tables_of_tree(cr) -> list[str]:
    cr.execute(
        """
        SELECT child.relname
          FROM pg_inherits
          JOIN pg_class child ON child.oid = pg_inherits.inhrelid
          JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
         WHERE parent.relname = 'resource_asset'
        """
    )
    return ["resource_asset", *(row[0] for row in cr.fetchall())]


def move_rows_into_subtype_table(cr, kind_code: str, table: str) -> int:
    """Parent to child is a DELETE and an INSERT, because PostgreSQL moves no
    row between them. An id survives it only because the whole tree shares one
    sequence, and the DELETE is possible only because the root holds no
    foreign key into it."""
    if not table_exists(cr, table):
        return 0
    cr.execute("SELECT id FROM resource_kind WHERE code = %s", [kind_code])
    row = cr.fetchone()
    if not row:
        return 0
    cr.execute(
        SQL(
            """
            WITH moved AS (
                DELETE FROM ONLY resource_asset asset
                 USING resource_resource resource
                 WHERE resource.id = asset.resource_id
                   AND resource.kind_id = %(kind)s
             RETURNING asset.*
            )
            INSERT INTO %(table)s SELECT * FROM moved
            """,
            kind=row[0],
            table=SQL.identifier(table),
        )
    )
    moved = cr.rowcount
    if moved:
        _debug.lifecycle("resource_asset.rows_moved", table=table, rows=moved)
        _logger.info(
            "resource_asset: moved %d %s row(s) into %s.", moved, kind_code, table
        )
    return moved

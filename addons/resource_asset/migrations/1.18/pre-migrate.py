from odoo.db.schema import column_exists, table_exists
from odoo.tools import SQL

# what a thing is and where it came from: the asset's columns, now the
# resource's, which shares the asset's id since 1.17
LIFTED = (
    "model",
    "model_year",
    "brand_new",
    "vendor_id",
    "vendor_ref",
    "warranty_date",
    "address_id",
)


def _tree_tables(cr):
    cr.execute(
        """
        WITH RECURSIVE tree(oid) AS (
            SELECT 'resource_asset'::regclass::oid
             UNION
            SELECT inherit.inhrelid FROM pg_inherits inherit
              JOIN tree ON inherit.inhparent = tree.oid
        )
        SELECT oid::regclass::text FROM tree
        """
    )
    return [row[0] for row in cr.fetchall()]


def _add_like(cr, column):
    if column_exists(cr, "resource_resource", column):
        return
    cr.execute(
        """
        SELECT format_type(atttypid, atttypmod) FROM pg_attribute
         WHERE attrelid = 'resource_asset'::regclass AND attname = %s
        """,
        [column],
    )
    cr.execute(
        SQL(
            "ALTER TABLE resource_resource ADD COLUMN %s %s",
            SQL.identifier(column),
            SQL(cr.fetchone()[0]),
        )
    )


def migrate(cr, version):
    if not version or not table_exists(cr, "resource_asset"):
        return
    columns = [c for c in LIFTED if column_exists(cr, "resource_asset", c)]
    for column in columns:
        _add_like(cr, column)
    if columns:
        cr.execute(
            SQL(
                "UPDATE resource_resource resource SET %s"
                " FROM resource_asset asset WHERE asset.id = resource.id",
                SQL(", ").join(
                    SQL("%s = asset.%s", SQL.identifier(c), SQL.identifier(c))
                    for c in columns
                ),
            )
        )
    if column_exists(cr, "resource_asset", "description"):
        # a room's booking text (calendar) may already be the resource's; the
        # asset's description fills a resource that has none
        _add_like(cr, "description")
        cr.execute(
            """
            UPDATE resource_resource resource SET description = asset.description
              FROM resource_asset asset
             WHERE asset.id = resource.id AND asset.description IS NOT NULL
               AND resource.description IS NULL
            """
        )
        columns.append("description")
    # a subtype table declares the root's columns as its own, so each one
    # drops its copy too
    for table in _tree_tables(cr):
        for column in columns:
            cr.execute(
                SQL(
                    "ALTER TABLE %s DROP COLUMN IF EXISTS %s",
                    SQL.identifier(table),
                    SQL.identifier(column),
                )
            )

from odoo.db.schema import column_exists, table_exists
from odoo.tools import SQL

LIFTED_COLUMNS = ("state", "state_before_maintenance")


def _asset_tree_tables(cr):
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


def _lift_asset_state(cr):
    for column in LIFTED_COLUMNS:
        if not column_exists(cr, "resource_resource", column):
            cr.execute(
                SQL(
                    "ALTER TABLE resource_resource ADD COLUMN %s varchar",
                    SQL.identifier(column),
                )
            )
    if not table_exists(cr, "resource_asset"):
        return
    columns = [c for c in LIFTED_COLUMNS if column_exists(cr, "resource_asset", c)]
    if not columns:
        return
    cr.execute(
        SQL(
            "UPDATE resource_resource resource SET %s"
            " FROM resource_asset asset WHERE asset.resource_id = resource.id",
            SQL(", ").join(
                SQL("%s = asset.%s", SQL.identifier(c), SQL.identifier(c))
                for c in columns
            ),
        )
    )
    # a subtype table declares the root's columns as its own, so dropping
    # them from the root leaves its copies behind
    for table in _asset_tree_tables(cr):
        for column in columns:
            cr.execute(
                SQL(
                    "ALTER TABLE %s DROP COLUMN IF EXISTS %s",
                    SQL.identifier(table),
                    SQL.identifier(column),
                )
            )


def migrate(cr, version):
    if not version:
        return
    _lift_asset_state(cr)
    # maintenance could be entered only from service before a resource
    # remembered the state it came from
    cr.execute(
        """
        UPDATE resource_resource
           SET state_before_maintenance = 'in_service'
         WHERE state = 'maintenance' AND state_before_maintenance IS NULL
        """
    )
    cr.execute("UPDATE resource_resource SET state = 'available' WHERE state IS NULL")

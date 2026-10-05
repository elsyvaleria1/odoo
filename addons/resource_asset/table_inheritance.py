from odoo.db.schema import column_exists, rename_column, table_exists


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

from odoo.db.schema import (
    column_exists,
    drop_views_depending_on_table,
    get_table_columns,
    table_exists,
)
from odoo.tools import SQL, module_data

ROOT = "resource_asset"
# the kinds whose models keep a table of their own, extending their resource
KIND_TABLES = ("resource_asset_vehicle", "resource_asset_room")
# the kinds whose models added only identifiers, which are the resource's
RETIRED = (
    "resource.asset.device",
    "resource.asset.equipment",
    "resource.asset.furniture",
    "resource.asset.it",
    "resource.asset.machinery",
    "resource.asset.property",
    "resource.asset.telecom",
)
TREE = ("resource.asset", *RETIRED)
# the root's stored copies of what the resource holds
COPIES = ("name", "active", "company_id")
KEPT = ("id", "resource_id", "create_uid", "create_date", "write_uid", "write_date")
# a column the resource already has is its module's to reconcile, from here
LEGACY = "resource_asset_legacy"


def _tree_tables(cr):
    cr.execute(
        """
        SELECT child.relname FROM pg_inherits
          JOIN pg_class child ON child.oid = pg_inherits.inhrelid
          JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
         WHERE parent.relname = %s
        """,
        [ROOT],
    )
    return [ROOT, *(row[0] for row in cr.fetchall())]


def migrate(cr, version):
    if not version or not table_exists(cr, ROOT):
        return
    # a thing is its resource: what the root still held is the resource's
    columns = [c for c in get_table_columns(cr, ROOT) if c not in (*KEPT, *COPIES)]
    held = [c for c in columns if column_exists(cr, "resource_resource", c)]
    if held:
        # every row of the tree, under its resource's id; end-migrate drops it
        cr.execute(
            SQL(
                "CREATE TABLE %s AS SELECT id, %s FROM %s",
                SQL.identifier(LEGACY),
                SQL(", ").join(SQL.identifier(c) for c in held),
                SQL.identifier(ROOT),
            )
        )
    lifted = [c for c in columns if c not in held]
    module_data.lift_columns(cr, ROOT, "resource_resource", lifted)
    tables = _tree_tables(cr)
    for column in COPIES:
        for table in tables:
            drop_views_depending_on_table(cr, table, column)
        cr.execute(
            SQL(
                "ALTER TABLE %s DROP COLUMN IF EXISTS %s",
                SQL.identifier(ROOT),
                SQL.identifier(column),
            )
        )
    # the models extending a kind leave the tree, under their resource's ids
    for table in KIND_TABLES:
        if table not in tables:
            continue
        sequence = f"{table}_id_seq"
        cr.execute(
            SQL(
                "ALTER TABLE %s NO INHERIT %s",
                SQL.identifier(table),
                SQL.identifier(ROOT),
            )
        )
        # the root's own check, inherited; the table keeps its own
        cr.execute(
            SQL(
                "ALTER TABLE %s DROP CONSTRAINT IF EXISTS %s",
                SQL.identifier(table),
                SQL.identifier(f"{ROOT}_inherits_shared_id"),
            )
        )
        cr.execute(
            SQL(
                "CREATE SEQUENCE IF NOT EXISTS %s OWNED BY %s",
                SQL.identifier(sequence),
                SQL.identifier(table, "id"),
            )
        )
        cr.execute(
            SQL(
                "SELECT setval(%s, COALESCE((SELECT max(id) FROM %s), 0) + 1, false)",
                sequence,
                SQL.identifier(table),
            )
        )
        cr.execute(
            SQL(
                "ALTER TABLE %s ALTER COLUMN id SET DEFAULT nextval(%s)",
                SQL.identifier(table),
                sequence,
            )
        )
    # a reference into the tree, held without a foreign key, names a resource
    # from here on, which refuses what names none
    module_data.clear_dangling_references(cr, TREE, "resource_resource")
    for table in tables:
        if table in KIND_TABLES:
            continue
        if table != ROOT:
            cr.execute(SQL("DROP TABLE %s", SQL.identifier(table)))
    cr.execute(SQL("DROP TABLE %s", SQL.identifier(ROOT)))
    for model in TREE:
        module_data.merge_model(cr, model, "resource.resource")
    # stored as a value, not as a model name column
    for table, column in (("document_type", "applies_to"),):
        if table_exists(cr, table):
            cr.execute(
                SQL(
                    "UPDATE %s SET %s = 'resource.resource' WHERE %s = 'resource.asset'",
                    SQL.identifier(table),
                    SQL.identifier(column),
                    SQL.identifier(column),
                )
            )
    # an image is the resource's, whichever kind model it was stored under
    cr.execute(
        """
        UPDATE ir_attachment SET res_model = 'resource.resource'
         WHERE res_model IN ('resource.asset.vehicle', 'resource.asset.room')
           AND res_field LIKE 'image\\_%'
        """
    )

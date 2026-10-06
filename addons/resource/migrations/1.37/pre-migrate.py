from odoo.db.schema import column_exists, table_exists
from odoo.tools import SQL, module_data

LIFTED_MODELS = (
    ("resource.asset.identifier.type", "resource.identifier.type"),
    ("resource.asset.identifier", "resource.identifier"),
    ("resource.asset.meter", "resource.meter"),
    ("resource.asset.meter.reading", "resource.meter.reading"),
)
REPOINTED_TABLES = (
    ("resource_identifier", "resource.identifier"),
    ("resource_meter", "resource.meter"),
)
LIFTED_COLUMNS = ("date_acquisition", "date_disposal", "value_original")
# resource_asset still declares this field on the lifted model
KEPT_BY_RESOURCE_ASSET = ("field_resource_identifier_type__kind_ids",)


def _drop_constraints_on(cr, table, column):
    cr.execute(
        """
        SELECT con.conname
          FROM pg_constraint con
          JOIN pg_attribute att
            ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
         WHERE con.conrelid = %s::regclass
           AND con.contype IN ('f', 'u')
           AND att.attname = %s
        """,
        [table, column],
    )
    for (name,) in cr.fetchall():
        cr.execute(
            SQL(
                "ALTER TABLE %s DROP CONSTRAINT %s",
                SQL.identifier(table),
                SQL.identifier(name),
            )
        )


def _lift_asset_models(cr):
    for old, new in LIFTED_MODELS:
        if table_exists(cr, old.replace(".", "_")) and not table_exists(
            cr, new.replace(".", "_")
        ):
            module_data.rename_model(cr, old, new)
    for table, model in REPOINTED_TABLES:
        if not column_exists(cr, table, "asset_id"):
            continue
        # the rows named an asset and name its resource now: the foreign key
        # into resource_asset would refuse them, and the unique key on the
        # column would collide mid-update; the ORM recreates both
        _drop_constraints_on(cr, table, "asset_id")
        cr.execute(
            SQL(
                "UPDATE %s lifted SET asset_id = asset.resource_id"
                " FROM resource_asset asset WHERE asset.id = lifted.asset_id",
                SQL.identifier(table),
            )
        )
        module_data.rename_field(cr, model, "asset_id", "resource_id")
    module_data.rename_field(cr, "resource.meter.reading", "asset_id", "resource_id")


def _take_lifted_records(cr):
    prefixes = [
        f"{kind}{table}__"
        for kind in ("field_", "selection__")
        for table in (new.replace(".", "_") for __, new in LIFTED_MODELS)
    ] + ["constraint_resource_identifier_", "constraint_resource_meter_"]
    models = [f"model_{new.replace('.', '_')}" for __, new in LIFTED_MODELS]
    cr.execute(
        """
        UPDATE ir_model_data source
           SET module = 'resource'
         WHERE source.module = 'resource_asset'
           AND (
                (source.model = 'ir.model' AND source.name = ANY(%(models)s))
             OR (source.model IN ('ir.model.fields', 'ir.model.fields.selection',
                                  'ir.model.constraint')
                 AND source.name LIKE ANY(%(prefixes)s))
             OR source.model = 'resource.identifier.type'
           )
           AND source.name <> ALL(%(kept)s)
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data target
                 WHERE target.module = 'resource' AND target.name = source.name
           )
        """,
        {
            "models": models,
            "prefixes": [prefix.replace("_", "\\_") + "%" for prefix in prefixes],
            "kept": list(KEPT_BY_RESOURCE_ASSET),
        },
    )


def _lift_asset_columns(cr):
    if not table_exists(cr, "resource_asset"):
        return
    columns = [c for c in LIFTED_COLUMNS if column_exists(cr, "resource_asset", c)]
    if not columns:
        return
    for column in columns:
        if column_exists(cr, "resource_resource", column):
            continue
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
    # them from the root leaves its copies, and their CHECKs, behind
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
    for (table,) in cr.fetchall():
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
    _lift_asset_models(cr)
    _take_lifted_records(cr)
    _lift_asset_columns(cr)

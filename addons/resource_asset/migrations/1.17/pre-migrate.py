from odoo.db.schema import column_exists, table_exists
from odoo.tools import module_data

SUBTYPES = ("mt_asset_operator_updated", "mt_asset_future_operator_scheduled")


def _tree_models(cr):
    # the root and every subtype table that inherits it in PostgreSQL; a
    # subtype model's table is its name with underscores
    cr.execute(
        """
        WITH RECURSIVE tree(oid) AS (
            SELECT 'resource_asset'::regclass::oid
             UNION
            SELECT inherit.inhrelid FROM pg_inherits inherit
              JOIN tree ON inherit.inhparent = tree.oid
        )
        SELECT model.model FROM ir_model model
          JOIN tree ON replace(model.model, '.', '_') = tree.oid::regclass::text
        """
    )
    return [row[0] for row in cr.fetchall()]


def migrate(cr, version):
    if not version or not table_exists(cr, "resource_asset"):
        return
    # an asset is its resource's row extended (`_inherits_shared_id`): it takes
    # its resource's id, and what was filed under the asset is the resource's
    models = _tree_models(cr)
    # a property value holds asset ids too, re-keyed once the registry knows
    # its definitions (end-migrate.py)
    cr.execute(
        "CREATE TABLE resource_asset_rekey_1_17 AS "
        "SELECT id AS old_id, resource_id AS new_id FROM resource_asset"
    )
    cr.execute("SELECT old_id, new_id FROM resource_asset_rekey_1_17")
    module_data.rekey_records(cr, models, "resource_asset", dict(cr.fetchall()))
    # mrp_maintenance 1.8 reads the equipment table no model declares any
    # more, by asset id
    if column_exists(cr, "maintenance_equipment", "asset_id"):
        cr.execute(
            """
            UPDATE maintenance_equipment equipment SET asset_id = move.new_id
              FROM resource_asset_rekey_1_17 move
             WHERE equipment.asset_id = move.old_id
            """
        )
    module_data.rehome_references(cr, models, "resource.resource")
    cr.execute(
        """
        UPDATE mail_message_subtype subtype SET res_model = 'resource.resource'
          FROM ir_model_data data
         WHERE data.module = 'resource_asset' AND data.name = ANY(%s)
           AND data.model = 'mail.message.subtype' AND data.res_id = subtype.id
        """,
        [list(SUBTYPES)],
    )

from odoo.db.schema import table_exists
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
    cr.execute("SELECT id, resource_id FROM resource_asset")
    module_data.rekey_records(cr, models, "resource_asset", dict(cr.fetchall()))
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

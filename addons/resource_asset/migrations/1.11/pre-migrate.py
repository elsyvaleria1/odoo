from odoo.db import schema


def migrate(cr, version):
    if not version or not schema.table_exists(cr, "resource_asset"):
        return
    cr.execute("""
        SELECT a.id FROM resource_asset a
          JOIN resource_resource r ON r.id = a.resource_id
         WHERE r.type != 'material'
         ORDER BY a.id LIMIT 10
    """)
    incompatible = [row[0] for row in cr.fetchall()]
    if incompatible:
        raise ValueError(
            "Resource ownership migration: assets refer to non-material resources; "
            f"reconcile asset identities {incompatible} before upgrading"
        )
    cr.execute("""
        SELECT resource_id
          FROM resource_asset
         WHERE resource_id IS NOT NULL
         GROUP BY resource_id
        HAVING count(*) > 1
         ORDER BY resource_id
         LIMIT 10
    """)
    duplicates = [row[0] for row in cr.fetchall()]
    if duplicates:
        raise ValueError(
            "Resource ownership migration: several owning records refer to "
            f"the same resource identities {duplicates}; reconcile them before upgrading"
        )

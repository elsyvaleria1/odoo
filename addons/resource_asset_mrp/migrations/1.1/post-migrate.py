from odoo import SUPERUSER_ID, api
from odoo.db import schema


def migrate(cr, version):
    if not version or not schema.column_exists(cr, "mrp_workcenter", "legacy_asset_id"):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.flush_all()
    cr.execute("""
        SELECT workcenter.id FROM mrp_workcenter workcenter
          LEFT JOIN resource_asset asset ON asset.id = workcenter.legacy_asset_id
         WHERE workcenter.legacy_asset_id IS NOT NULL
           AND (asset.id IS NULL OR asset.resource_id IS DISTINCT FROM workcenter.resource_id)
         LIMIT 1
    """)
    if cr.fetchone():
        raise ValueError(
            "Work center identity migration: missing machine or conflicting resource identity; reconcile before upgrading"
        )
    resources = (
        env["mrp.workcenter"].with_context(active_test=False).search([]).resource_id
    )
    resources._check_host_type("material")
    cr.execute("ALTER TABLE mrp_workcenter DROP COLUMN legacy_asset_id")

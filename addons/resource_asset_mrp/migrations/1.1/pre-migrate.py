from odoo.db import schema


def migrate(cr, version):
    if version and schema.column_exists(cr, "mrp_workcenter", "asset_id"):
        schema.rename_column(cr, "mrp_workcenter", "asset_id", "legacy_asset_id")

from odoo.addons.resource_asset.table_inheritance import set_aside_root_columns


def migrate(cr, version):
    if version:
        set_aside_root_columns(cr, ["parent_id"])

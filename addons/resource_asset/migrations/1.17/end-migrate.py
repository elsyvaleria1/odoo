from odoo import SUPERUSER_ID, api
from odoo.db.schema import table_exists
from odoo.tools import module_data


def migrate(cr, version):
    if not version or not table_exists(cr, "resource_asset_rekey_1_17"):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    tree = [
        name
        for name, model in env.registry.items()
        if model._table_inheritance_root == "resource_asset"
    ]
    cr.execute("SELECT old_id, new_id FROM resource_asset_rekey_1_17")
    module_data.rekey_property_values(env, tree, dict(cr.fetchall()))
    cr.execute("DROP TABLE resource_asset_rekey_1_17")

from odoo.db.schema import table_exists
from odoo.tools import module_data


def migrate(cr, version):
    if not version or not table_exists(cr, "resource_asset"):
        return
    module_data.lift_columns(
        cr,
        "resource_asset",
        "resource_resource",
        ["location", "value_residual", "account_prefix", "area"],
    )

from odoo.db.schema import table_exists
from odoo.tools import module_data


def migrate(cr, version):
    if not version or not table_exists(cr, "resource_asset"):
        return
    # a thing's kind, and the properties its kind defines, are its resource's
    module_data.rename_field(
        cr, "resource.kind", "asset_properties_definition", "properties_definition"
    )
    module_data.lift_columns(
        cr,
        "resource_asset",
        "resource_resource",
        ["kind_id", ("asset_properties", "properties")],
    )

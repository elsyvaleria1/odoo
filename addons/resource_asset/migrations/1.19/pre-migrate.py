from odoo.db.schema import table_exists
from odoo.tools import module_data

# a thing's odometer: the asset's columns, now the resource's, which shares the
# asset's id
LIFTED = ("odometer", "odometer_uom_id", "odometer_meter_id")


def migrate(cr, version):
    if not version or not table_exists(cr, "resource_asset"):
        return
    module_data.lift_columns(cr, "resource_asset", "resource_resource", LIFTED)

from odoo.db.schema import table_exists
from odoo.tools import module_data

# what a thing is and where it came from: the asset's columns, now the resource's,
# which shares the asset's id since 1.17; a room's booking description
# (calendar) already on its resource is kept
LIFTED = (
    "model",
    "model_year",
    "brand_new",
    "vendor_id",
    "vendor_ref",
    "warranty_date",
    "address_id",
    "description",
)


def migrate(cr, version):
    if not version or not table_exists(cr, "resource_asset"):
        return
    module_data.lift_columns(
        cr, "resource_asset", "resource_resource", LIFTED, keep_target=("description",)
    )

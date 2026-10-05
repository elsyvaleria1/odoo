from odoo.db.schema import table_exists
from odoo.tools import module_data

DOCUMENT_SLOTS = (
    "fuel_card",
    "highway_pass",
    "property_deed",
    "lease_agreement",
    "building_permit",
)


def migrate(cr, version):
    if not version or not table_exists(cr, "resource_asset"):
        return
    module_data.lift_columns(
        cr,
        "resource_asset",
        "resource_resource",
        [f"{slot}_{suffix}" for slot in DOCUMENT_SLOTS for suffix in ("id", "name")],
    )

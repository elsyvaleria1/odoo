from . import models
from . import wizards
from . import reports


def _create_warehouse_data(env) -> None:
    warehouses = env["stock.warehouse"].search([("repair_type_id", "=", False)])
    for warehouse in warehouses:
        picking_type_vals = warehouse._create_or_update_picking_types()
        if picking_type_vals:
            warehouse.write(picking_type_vals)

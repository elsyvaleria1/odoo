from . import models


def _pos_restaurant_appointment_after_init(env) -> None:
    table_ids = env["restaurant.table"].search([("resource_id", "=", False)])
    for table_id in table_ids:
        table_id.resource_id = (
            table_id.env["resource.resource"]
            .sudo()
            .create(
                {
                    "name": f"{table_id.floor_id.name} - {table_id.table_number}",
                    "type": "material",
                    "capacity": table_id.seats,
                    "pos_table_ids": table_id,
                }
            )
        )

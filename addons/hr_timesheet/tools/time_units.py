from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo.api import Environment


def hours_to_days(env: Environment, hours: float) -> float:
    """Convert using the configured time units and round for timesheet display."""
    uom_hour = env.ref("base.product_uom_hour")
    uom_day = env.ref("base.product_uom_day")
    return round(
        uom_hour._get_quantity_in_unit(hours, uom_day, raise_if_failure=False), 2
    )

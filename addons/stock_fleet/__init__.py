from odoo.tools.authority_keys import declare_authority_keys

from . import models
from . import wizards
from .models.stock_picking_batch_trip import TRIP_DEPARTURE_DATE, TRIP_RETURN_DATE
from .models.stock_picking_trip import (
    MERGE_TRIPS,
    UNBATCH_CORRECTION,
    UNBATCH_UNDELIVERED,
)

# Backdating a trip is for the server's own readers, never for a client.
declare_authority_keys("stock_fleet", TRIP_DEPARTURE_DATE, TRIP_RETURN_DATE)
# Taking a transfer off a departed trip, or moving it to another trip, is the
# server's: the not-delivered and correction wizards, and merging trips.
declare_authority_keys(
    "stock_fleet", UNBATCH_UNDELIVERED, UNBATCH_CORRECTION, MERGE_TRIPS
)


def _enable_dispatch_management(env) -> None:
    for delivery_steps, warehouses in env["stock.warehouse"]._read_group(
        [], ["delivery_steps"], ["id:recordset"]
    ):
        if delivery_steps == "pick_pack_ship":
            warehouses.pack_type_id.dispatch_management = True
        elif delivery_steps == "pick_ship":
            warehouses.pick_type_id.dispatch_management = True

        warehouses.out_type_id.dispatch_management = True
        warehouses.in_type_id.dispatch_management = True

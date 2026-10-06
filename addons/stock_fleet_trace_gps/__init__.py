from odoo.tools.authority_keys import declare_authority_keys

from . import models

# A GPS reading dates and places a checkpoint: the server's reader sets it, never
# a client.
declare_authority_keys("stock_fleet_trace_gps", "trip_gps_reading")

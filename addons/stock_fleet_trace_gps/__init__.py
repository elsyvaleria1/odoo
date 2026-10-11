from odoo.tools.authority_keys import declare_authority_keys

from . import models

declare_authority_keys("stock_fleet_trace_gps", "trip_gps_reading")

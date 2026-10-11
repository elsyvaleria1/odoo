from odoo.tools.authority_keys import declare_authority_keys

from . import controllers
from . import models
from . import wizards

declare_authority_keys(
    "stock_fleet_trace",
    "trip_checkpoint_method",
    "trip_handover",
    "trip_offline_applying",
    "trip_offline_capture",
    "trip_returning",
)

from odoo.tools.authority_keys import declare_authority_keys

from . import controllers
from . import models
from . import wizards

# The trip's log is tamper-evident: when, where and how a checkpoint was taken,
# and the guards a handover or a return lifts, are for the server's own flows,
# never for a client.
declare_authority_keys(
    "stock_fleet_trace",
    "trip_checkpoint_method",
    "trip_handover",
    "trip_offline_applying",
    "trip_offline_capture",
    "trip_returning",
)

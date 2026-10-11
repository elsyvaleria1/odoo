from odoo.http import register_routing_parameters

register_routing_parameters("check_identity")

from . import controllers
from . import models

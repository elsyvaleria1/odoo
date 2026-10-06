from odoo.http import register_select_db_paths

from . import controllers
from . import models
from . import wizards
from . import reports

register_select_db_paths("/odoo", "/web", "/web/login", prefixes=("/odoo/",))

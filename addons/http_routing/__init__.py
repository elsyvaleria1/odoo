from . import controllers
from . import models

from odoo.http import request


def _post_init_hook(env) -> None:
    if request:
        request.is_frontend = False
        request.is_frontend_multilang = False

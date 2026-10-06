from . import models
from odoo.tools import convert


def _pos_restaurant_preparation_display_post_init(env) -> None:
    env["pos.config"]._init_preparation_display_data()

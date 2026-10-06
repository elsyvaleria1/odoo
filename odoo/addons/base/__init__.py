from . import models
from . import wizards


def post_init(env) -> None:
    env["ir.config_parameter"].init(force=True)

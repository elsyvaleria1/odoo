from . import tools
from . import controllers
from . import models


def post_init_hook(env) -> None:
    env["res.company"]._update_presence_control_config(True)


def uninstall_hook(env):
    env["res.company"]._update_presence_control_config(False)

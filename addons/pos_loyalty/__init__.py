from . import models


def uninstall_hook(env):
    env["loyalty.history"].search([("order_model", "=", "pos.order")]).unlink()

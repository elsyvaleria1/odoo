from . import models
from . import reports
from . import wizards


def post_init_hook(env) -> None:
    env["account.analytic.plan"].search([])._sync_all_plan_column()

from . import models
from . import wizards


def _post_init_hook_setup_issuing_demo(env) -> None:
    env["ir.config_parameter"].set_param("hr_expense_stripe.stripe_mode", "test")

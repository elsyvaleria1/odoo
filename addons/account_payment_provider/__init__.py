from . import controllers
from . import models
from . import wizards


def post_init_hook(env) -> None:
    PaymentProvider = env["payment.provider"]
    installed_providers = PaymentProvider.search(
        [("module_id.state", "=", "installed")]
    )
    for code in set(installed_providers.mapped("code")):
        PaymentProvider._setup_payment_method(code)


def uninstall_hook(env):
    installed_providers = env["payment.provider"].search(
        [("module_id.state", "=", "installed")]
    )
    env["account.payment.method"].search(
        [
            ("code", "in", installed_providers.mapped("code")),
            ("payment_type", "=", "inbound"),
        ]
    ).unlink()

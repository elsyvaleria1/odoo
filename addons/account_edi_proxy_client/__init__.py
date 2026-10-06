from . import models


def _create_demo_config_param(env) -> None:
    env["ir.config_parameter"].set_param("account_edi_proxy_client.demo", "demo")

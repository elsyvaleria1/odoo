from . import models


def _post_init_hook(env):
    if env.context.get("install_mode"):
        module = env["ir.module.module"].search(
            [("name", "=", "test_automation")], limit=1
        )
        if module and module.demo:
            from .demo import demo_data

            demo_data._setup_demo_data(env)

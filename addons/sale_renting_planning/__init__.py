from . import models


def uninstall_hook(env):
    env["planning.slot"].search(
        [
            ("sale_line_id", "!=", False),
            ("sale_line_id.is_rental", "=", True),
        ]
    ).unlink()

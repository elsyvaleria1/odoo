from odoo.api import Environment

from . import models


def _forbid_self_approval(env: Environment) -> None:
    category = env.ref(
        "approval_base_install_request.approval_category_module_activation",
        raise_if_not_found=False,
    )
    if category:
        category.allow_self_approval = False

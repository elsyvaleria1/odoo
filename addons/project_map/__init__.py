from . import models

from odoo.addons.project.models.ir_actions_act_window import (
    TASK_ACTIONS_WITH_ALL_VIEWS,
)


def _project_map_uninstall_hook(env) -> None:
    env["ir.actions.act_window"]._remove_view_mode(TASK_ACTIONS_WITH_ALL_VIEWS, "map")

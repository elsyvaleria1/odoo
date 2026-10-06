from . import models

from odoo.addons.project.models.ir_actions_act_window import (
    PROJECT_ACTIONS_WITH_ALL_VIEWS,
    TASK_ACTIONS_WITH_ALL_VIEWS,
)


def _project_gantt_uninstall_hook(env) -> None:
    act_window = env["ir.actions.act_window"]
    act_window._remove_view_mode(TASK_ACTIONS_WITH_ALL_VIEWS, "gantt")
    act_window._remove_view_mode(PROJECT_ACTIONS_WITH_ALL_VIEWS, "gantt")

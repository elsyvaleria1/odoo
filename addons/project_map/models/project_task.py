from odoo import api, fields, models
from odoo.tools import format_list


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = "project.task"

    user_names = fields.Char(
        export_string_translation=False,
        compute="_compute_user_names",
    )

    @api.depends("user_ids.name")
    def _compute_user_names(self) -> None:
        for task in self:
            task.user_names = format_list(self.env, task.user_ids.mapped("name"))

    def action_view_overlapping_tasks(self):
        action = super().action_view_overlapping_tasks()
        if "views" in action:
            map_view = self.env.ref("project_map.project_task_map_view_no_title")
            views = [
                (view_id, view_type)
                for view_id, view_type in action["views"]
                if view_type != "map"
            ]
            after_gantt = next(
                (i for i, (_id, kind) in enumerate(views) if kind == "gantt"), -1
            )
            views.insert(after_gantt + 1, (map_view.id, "map"))
            action["views"] = views
        return action

    def action_dependent_tasks(self):
        action = super().action_dependent_tasks()
        action["view_mode"] = self._add_map_view_mode(action["view_mode"])
        return action

    def action_recurring_tasks(self):
        action = super().action_recurring_tasks()
        action["view_mode"] = self._add_map_view_mode(action["view_mode"])
        return action

    def _add_map_view_mode(self, view_mode) -> str:
        modes = view_mode.split(",")
        if "map" not in modes:
            modes.append("map")
        return ",".join(modes)

from odoo import models


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = "project.project"

    def action_view_tasks(self):
        action = super().action_view_tasks()
        if not self.allow_milestones:
            action["views"] = [
                (
                    view_id
                    if view_type != "map"
                    else self.env.ref(
                        "project_map.project_task_map_view_no_title_no_milestone"
                    ).id,
                    view_type,
                )
                for view_id, view_type in action["views"]
            ]
        if self._is_partner_hidden() or self.is_template:
            action["views"] = [
                (view_id, view_type)
                for view_id, view_type in action["views"]
                if view_type != "map"
            ]
        return action

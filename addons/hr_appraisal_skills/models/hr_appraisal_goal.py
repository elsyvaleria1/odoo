from odoo import Command, fields, models
from odoo.api import ValuesType


class HrAppraisalGoal(models.Model):
    _name = "hr.appraisal.goal"
    _inherit = ["mixin.hr.individual.skill.owner", "hr.appraisal.goal"]

    goal_skill_ids = fields.One2many(
        comodel_name="hr.appraisal.goal.skill",
        inverse_name="goal_id",
        string="Skills",
        domain=[("skill_type_id.active", "=", True)],
    )
    current_goal_skill_ids = fields.One2many(
        comodel_name="hr.appraisal.goal.skill",
        compute="_compute_current_individual_skill_ids",
        search="_search_current_individual_skill_ids",
        readonly=False,
        help="This goal will be recommended to reach the level of those skills.",
    )

    def _individual_skill_field_name(self):
        return "goal_skill_ids"

    def _current_individual_skill_field_name(self):
        return "current_goal_skill_ids"

    def _prepare_goal_vals(self, employee_id, goal_parent_id) -> ValuesType:
        self.check_singleton()
        res = super()._prepare_goal_vals(employee_id, goal_parent_id)
        # Need to use this method instead of copy because it's not possible to duplicate a hr.appraisal.goal.skill
        skill_values = self.current_goal_skill_ids.read(load=False)
        for skill_value in skill_values:
            skill_value["goal_id"] = False
        res.update(
            {
                "goal_skill_ids": [
                    Command.create(skill_value) for skill_value in skill_values
                ]
            }
        )
        return res

    def copy(self, default=None):
        new_goals = super().copy(default)

        new_goal_by_old_goal = dict(zip(self.ids, new_goals.ids, strict=False))
        # Need to use this method instead of copy because it's not possible to duplicate a hr.appraisal.goal.skill
        new_skill_values = self.goal_skill_ids.read(load=False)

        for new_skill_value in new_skill_values:
            old_goal_id = new_skill_value["goal_id"]
            new_skill_value["goal_id"] = new_goal_by_old_goal[old_goal_id]

        self.env["hr.appraisal.goal.skill"].create(new_skill_values)
        return new_goals

from odoo import fields, models


class HrAppraisalGoalSkill(models.Model):
    _name = "hr.appraisal.goal.skill"
    _inherit = "mixin.hr.individual.skill"
    _description = "Skills for goal positions"
    _order = "skill_type_id, skill_level_id desc"

    goal_id = fields.Many2one(
        comodel_name="hr.appraisal.goal",
        index=True,
        required=True,
        ondelete="cascade",
    )

    def _linked_field_name(self):
        return "goal_id"

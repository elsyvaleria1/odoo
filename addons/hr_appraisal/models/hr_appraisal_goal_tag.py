from odoo import api, models


class HrAppraisalGoalTag(models.Model):
    _name = "hr.appraisal.goal.tag"
    _description = "Appraisal Goal Tags"
    _inherit = ["mixin.tag"]

    @api.model
    def name_create(self, name):
        existing_tag = self.search([("name", "=ilike", name.strip())], limit=1)
        if existing_tag:
            return existing_tag.id, existing_tag.name
        return super().name_create(name)

from odoo import api, models


class HrAppraisalGoalTag(models.Model):
    _name = "hr.appraisal.goal.tag"
    _description = "Appraisal Goal Tags"
    # `name`, `active`, `color` and `code` come from the mixin: `code` is the
    # unique, untranslated identifier; `name` is not translated either. Flat:
    # goal tags do not nest.
    _inherit = ["mixin.tag"]

    @api.model
    def name_create(self, name):
        existing_tag = self.search([("name", "=ilike", name.strip())], limit=1)
        if existing_tag:
            return existing_tag.id, existing_tag.name
        return super().name_create(name)

from odoo import api, models


class HelpdeskTag(models.Model):
    _name = "helpdesk.tag"
    _description = "Helpdesk Tags"
    _inherit = ["mixin.tag"]

    @api.model
    def name_create(self, name):
        existing_tag = self.search([("name", "=ilike", name.strip())], limit=1)
        if existing_tag:
            return existing_tag.id, existing_tag.display_name
        return super().name_create(name)

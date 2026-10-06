from odoo import api, models


class HelpdeskTag(models.Model):
    _name = "helpdesk.tag"
    _description = "Helpdesk Tags"
    # `name` (translated, unique on the source term), `active`, `color` and
    # `code` come from the mixin, which already carried the uniqueness rule this
    # model was importing on its own. Flat: helpdesk tags do not nest.
    _inherit = ["mixin.tag"]

    @api.model
    def name_create(self, name):
        existing_tag = self.search([("name", "=ilike", name.strip())], limit=1)
        if existing_tag:
            return existing_tag.id, existing_tag.display_name
        return super().name_create(name)

from odoo import api, models
from odoo.fields import Domain


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    @api.model
    def _get_domain_default_view(self, model, view_type):
        return super()._get_domain_default_view(model, view_type) & Domain(
            "name", "!=", "calendar.event.view.gantt.kanban.popover"
        )

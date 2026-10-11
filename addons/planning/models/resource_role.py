from odoo import fields, models
from odoo.libs.colors import PLANNING_COLORS


class ResourceRole(models.Model):
    """Planning's additions to the shared `resource.role`: shift properties and Gantt presentation."""

    _inherit = "resource.role"

    slot_properties_definition = fields.PropertiesDefinition(
        string="Planning Slot Properties"
    )

    def _get_color_from_code(self, is_open_shift):
        color = self._color_index_to_hex(self.color, palette=PLANNING_COLORS)
        if color is False:
            raise KeyError(self.color)
        return color + ("80" if is_open_shift else "")

    def _get_light_color(self, factor, is_open_shift):
        return self._lighten_color(self._get_color_from_code(False), factor)

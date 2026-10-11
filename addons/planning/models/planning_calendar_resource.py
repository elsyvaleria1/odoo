from typing import Any

from odoo import fields, models
from odoo.tools import frozendict


class PlanningCalendarResource(models.Model):
    """Personnal calendar resource filter"""

    _name = "planning.calendar.resource"
    _description = "planning calendar resource"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Me",
        export_string_translation=False,
        default=lambda self: self.env.user,
        required=True,
        ondelete="cascade",
    )
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        string="resource",
        export_string_translation=False,
    )
    active = fields.Boolean(
        export_string_translation=False,
        default=True,
    )
    resource_type = fields.Selection(
        related="resource_id.type",
        export_string_translation=False,
    )
    checked = fields.Boolean(
        export_string_translation=False,
        default=True,
    )

    def get_or_create_calendar_filters(
        self, user_id: int, field_names: list[str]
    ) -> list[dict[str, Any]]:
        field_names = [*field_names, "resource_type"]
        if not self.env["planning.calendar.resource"].search_count(
            [("user_id", "=", user_id), ("resource_id", "=", False)], limit=1
        ):
            self.env["planning.calendar.resource"].create(
                {"resource_id": False, "user_id": user_id}
            )
        return self.search_read(domain=[("user_id", "=", user_id)], fields=field_names)

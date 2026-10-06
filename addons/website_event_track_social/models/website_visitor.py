from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WebsiteVisitor(models.Model):
    _inherit = "website.visitor"

    event_track_push_enabled_ids = fields.Many2many(
        comodel_name="event.track",
        string="Push Enabled Tracks",
        compute="_compute_event_track_push_enabled_ids",
        search="_search_event_track_push_enabled_ids",
        compute_sudo=True,
        groups="event.group_event_user",
        help="Tracks that are 'default favorited' can be blacklisted and the visitor is removed from push reminders.",
    )

    @api.depends("event_track_visitor_ids.track_id")
    def _compute_event_track_push_enabled_ids(self) -> None:
        results = self.env["event.track.visitor"]._read_group(
            [("visitor_id", "in", self.ids), ("is_blacklisted", "!=", True)],
            ["visitor_id"],
            ["track_id:array_agg"],
        )
        track_ids_map = {visitor.id: track_ids for visitor, track_ids in results}
        for visitor in self:
            visitor.event_track_push_enabled_ids = track_ids_map.get(visitor.id, [])

    def _search_event_track_push_enabled_ids(self, operator, operand) -> list:
        if operator == "not in":
            _debug.logic("push_search_refused", operator=operator)
            raise UserError(
                self.env._(
                    "Unsupported 'Not In' operation on track push enabled tracks"
                )
            )

        subquery = (
            self.env["event.track.visitor"]
            .sudo()
            ._search([("track_id", operator, operand), ("is_blacklisted", "=", True)])
        )
        return [("id", "not in", subquery.subselect("visitor_id"))]

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WebsiteVisitor(models.Model):
    _inherit = "website.visitor"

    calendar_event_ids = fields.One2many(
        comodel_name="calendar.event",
        inverse_name="visitor_id",
    )
    phone_ids = fields.Many2many(
        comodel_name="phone.number",
        related=None,
        compute="_compute_email_phone",
        compute_sudo=True,
    )

    @api.depends("calendar_event_ids", "partner_id.phone_ids")
    def _compute_email_phone(self) -> None:
        super()._compute_email_phone()
        for visitor in self:
            visitor.phone_ids = visitor.partner_id.phone_ids

        left_visitors = self.filtered(
            lambda visitor: not visitor.email or not visitor.phone_ids
        )
        last_booker_by_visitor = dict(
            self.env["calendar.event"]._read_group(
                [("visitor_id", "in", left_visitors.ids)],
                ["visitor_id"],
                ["appointment_booker_id:max"],
            )
        )
        ResPartner = self.env["res.partner"].with_prefetch(
            last_booker_by_visitor.values()
        )
        _debug.pipeline(
            "email_phone_fallback",
            visitors=self,
            incomplete=len(left_visitors),
            bookers_found=len(last_booker_by_visitor),
        )

        for visitor in left_visitors:
            if appointment_booker_id := last_booker_by_visitor.get(visitor):
                appointment_booker = ResPartner.browse(appointment_booker_id)
                visitor.email = appointment_booker.email
                visitor.phone_ids = appointment_booker.phone_ids

    def _merge_visitor(self, target):
        if self.calendar_event_ids:
            _debug.lifecycle(
                "events_reassigned",
                visitor=self,
                target=target,
                events=self.calendar_event_ids,
            )
            self.calendar_event_ids.write({"visitor_id": target.id})
        return super()._merge_visitor(target)

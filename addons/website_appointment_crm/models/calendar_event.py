from odoo import Command, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    def _prepare_lead_vals(self, partner):
        lead_values = super()._prepare_lead_vals(partner)
        visitor_sudo = self.env["website.visitor"]._get_visitor_from_request()
        if visitor_sudo and (
            not visitor_sudo.partner_id or visitor_sudo.partner_id == partner
        ):
            lead_values["visitor_ids"] = [Command.link(visitor_sudo.id)]
            if not lead_values.get("country_id") and visitor_sudo.country_id:
                lead_values["country_id"] = visitor_sudo.country_id.id
            if not lead_values.get("lang_id") and visitor_sudo.lang_id:
                lead_values["lang_id"] = visitor_sudo.lang_id.id
            _debug.logic(
                "lead_enriched_from_visitor",
                event=self,
                visitor=visitor_sudo,
                country=visitor_sudo.country_id,
                lang=visitor_sudo.lang_id,
            )
        return lead_values

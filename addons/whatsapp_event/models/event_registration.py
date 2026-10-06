from odoo import fields, models


class EventRegistration(models.Model):
    _inherit = "event.registration"

    date_tz = fields.Selection(related="event_id.date_tz")

    def _whatsapp_get_portal_url(self):
        """Return website_url if website_event is installed (introspect fields
        to avoid yet another bridge module)"""
        self.check_singleton()
        if "website_url" in self.event_id:
            return self.event_id.website_url
        return super()._whatsapp_get_portal_url()

    def _whatsapp_get_responsible(
        self, related_message=False, related_record=False, whatsapp_account=False
    ):
        if self.event_user_id:
            return self.event_user_id

        return super()._whatsapp_get_responsible(
            related_message, related_record, whatsapp_account
        )

    def _get_fields_whatsapp_safe(self) -> set:
        return {
            "name",
            "event_id.name",
            "event_id.organizer_id.name",
            "event_date_range",
            "event_id.user_id.name",
            "event_id.user_id.phone_ids",
            "event_id.address_id.city",
            "event_id.address_id.name",
            "event_id.address_id.contact_address_complete",
            "event_id.address_id.partner_latitude",
            "event_id.address_id.partner_longitude",
        }

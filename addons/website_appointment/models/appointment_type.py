from odoo import api, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.website_appointment.controllers.appointment import WebsiteAppointment

_debug = DebugLog(__name__)


class AppointmentType(models.Model):
    _name = "appointment.type"
    _inherit = [
        "appointment.type",
        "mixin.website.seo.metadata",
        "mixin.website.published.multi",
        "mixin.website.searchable",
    ]

    def _compute_website_url(self) -> None:
        super()._compute_website_url()
        for appointment_type in self:
            if appointment_type.id:
                appointment_type.website_url = "/appointment/%s" % appointment_type.id
            else:
                appointment_type.website_url = False

    def create_and_get_website_url(self, **kwargs):
        if "appointment_tz" not in kwargs:
            website_visitor = self.env["website.visitor"]._get_visitor_from_request(
                force_create=False
            )
            kwargs["appointment_tz"] = (
                self.env.user.tz or website_visitor.timezone or "UTC"
            )
            _debug.lifecycle(
                "timezone_defaulted",
                tz=kwargs["appointment_tz"],
                from_user=bool(self.env.user.tz),
                visitor=website_visitor,
            )

        with _debug.perf("create_and_get_website_url", cr=self.env.cr):
            return super().create_and_get_website_url(**kwargs)

    def copy_data(self, default=None):
        default = dict(default or {})
        default["is_published"] = False
        _debug.lifecycle("copy_unpublished", appointment_types=self)
        return super().copy_data(default=default)

    def get_backend_menu_id(self):
        return self.env.ref("calendar.mail_menu_calendar").id

    @api.model
    def _search_get_detail(self, website, order, options):
        invite_token = options.get("invite_token")
        allowed_appointment_type_ids = (
            WebsiteAppointment._get_checked_private_appointment_types(
                options.get("filter_appointment_type_ids"),
                options.get("filter_staff_user_ids"),
                options.get("filter_resource_ids"),
                invite_token,
                domain=WebsiteAppointment._appointments_base_domain(
                    filter_appointment_type_ids=options.get(
                        "filter_appointment_type_ids"
                    ),
                    search=options.get("search"),
                    invite_token=invite_token,
                    additional_domain=WebsiteAppointment._appointment_website_domain(
                        self
                    ),
                    filter_countries=True,
                ),
            ).ids
        )

        domain = [[("id", "in", allowed_appointment_type_ids)]]
        _debug.pipeline(
            "search_detail",
            allowed=len(allowed_appointment_type_ids),
            invited=bool(invite_token),
            with_description=bool(options["displayDescription"]),
        )

        search_fields = ["name"]
        mapping = {
            "name": {"name": "name", "type": "text", "match": True},
            "website_url": {
                "name": "website_url",
                "type": "url",
                "truncate": False,
                "html": False,
            },
        }

        mapping["detail"] = {
            "name": "appointment_duration_formatted",
            "type": "text",
            "html": True,
        }
        if options["displayDescription"]:
            mapping["description"] = {
                "name": "message_intro",
                "type": "text",
                "html": True,
                "truncate": True,
            }

        return {
            "base_domain": domain,
            "fetch_fields": [value["name"] for value in mapping.values()],
            "icon": "fa-calendar",
            "mapping": mapping,
            "model": "appointment.type",
            "requires_sudo": bool(invite_token),
            "search_fields": search_fields,
        }

    def action_share_invite(self):
        action = super().action_share_invite()
        if self.env.user.has_group("website.group_multi_website"):
            website_id = self.website_id
        else:
            website_id = self.env["website"]
        action["context"].update({"default_website_id": website_id.id})
        _debug.logic(
            "share_invite_website",
            appointment_types=self,
            website=website_id,
            multi_website=bool(website_id),
        )
        return action

    def _prepare_calendar_event_values(
        self,
        asked_capacity,
        booking_line_values,
        description,
        duration,
        allday,
        appointment_invite,
        guests,
        name,
        customer,
        staff_user,
        start,
        stop,
    ):
        values = super()._prepare_calendar_event_values(
            asked_capacity,
            booking_line_values,
            description,
            duration,
            allday,
            appointment_invite,
            guests,
            name,
            customer,
            staff_user,
            start,
            stop,
        )
        if self.env.user._is_public() and (
            visitor := self.env["website.visitor"]._get_visitor_from_request()
        ):
            values["visitor_id"] = visitor.id
            _debug.lifecycle(
                "event_bound_to_visitor", appointment_type=self, visitor=visitor
            )
        return values

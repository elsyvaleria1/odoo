from odoo import api, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from odoo.addons.website_appointment.controllers.appointment import WebsiteAppointment

_debug = DebugLog(__name__)


class WebsiteSnippetFilter(models.Model):
    _inherit = "website.snippet.filter"

    def _get_hardcoded_sample(self, model):
        if model._name != "appointment.type":
            return super()._get_hardcoded_sample(model)

        return [
            {
                "message_intro": self.env._(
                    "A first step in joining our team as a technical consultant."
                ),
                "name": self.env._("Candidate Interview"),
            },
            {
                "name": self.env._("Online Cooking Lesson"),
            },
            {
                "name": self.env._("Tennis Court"),
            },
        ]

    def _prepare_values(self, limit=None, search_domain=None, **options):
        if self.model_name == "appointment.type":
            if country := WebsiteAppointment._get_customer_country():
                customer_country_domain = Domain(
                    "country_ids", "in", [False, country.id]
                )
                search_domain = (
                    Domain(search_domain or Domain.TRUE) & customer_country_domain
                )
                _debug.logic("filter_by_customer_country", country=country, limit=limit)
        return super()._prepare_values(
            limit=limit, search_domain=search_domain, **options
        )

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if (
            "field_names" in defaults
            and self.env.context.get("model") == "appointment.type"
        ):
            defaults["field_names"] = "name,category"
        return defaults

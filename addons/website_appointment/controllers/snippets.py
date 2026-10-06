import datetime

from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AppointmentSnippets(http.Controller):
    @http.route("/appointment/get_snippet_data", type="jsonrpc", auth="user")
    def get_snippet_data(self, appointment_type_id=None):
        current_website = request.env["website"].get_current_website()
        domain = [
            ("website_published", "=", True),
            ("staff_user_ids", "!=", False),
            "|",
            ("end_datetime", "=", False),
            ("end_datetime", ">=", datetime.datetime.now()),
            "|",
            ("website_id", "=", current_website.id),
            ("website_id", "=", False),
        ]
        if appointment_type_id:
            appointment_types = (
                request.env["appointment.type"]
                .browse(appointment_type_id)
                .filtered_domain(domain)
            )
        else:
            appointment_types = request.env["appointment.type"].search(domain)

        _debug.pipeline(
            "snippet_data",
            website=current_website,
            requested=appointment_type_id,
            appointment_types=appointment_types,
        )
        return {
            appointment_type.id: {
                "id": appointment_type.id,
                "name": appointment_type.name,
                "staff_users": appointment_type.staff_user_ids.mapped(
                    lambda user: {"id": user.id, "name": user.name}
                ),
            }
            for appointment_type in appointment_types
        }

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request
from odoo.tools.urls import keep_query


class AppointmentLegacy(http.Controller):

    @http.route(
        ["/calendar/<string:appointment_type>/appointment"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def calendar_appointment(self, appointment_type, **kwargs):
        appointment_type_id = request.env["ir.http"]._unslug(appointment_type)[1]
        if not appointment_type_id:
            raise NotFound
        return request.redirect(
            "/calendar/%s?%s" % (appointment_type_id, keep_query("*"))
        )

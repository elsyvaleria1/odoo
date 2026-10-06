from odoo import http
from odoo.http import request


class WellKnownController(http.Controller):
    @http.route("/.well-known/carddav", type="http", auth="public")
    def well_known_carddav(self):
        return request.redirect("/dav/addressbooks/", code=301)

    @http.route("/.well-known/caldav", type="http", auth="public")
    def well_known_caldav(self):
        return request.redirect("/dav/calendars/", code=301)

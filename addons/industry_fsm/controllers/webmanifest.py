from odoo.http import request

from odoo.addons.web.controllers import webmanifest


class WebManifest(webmanifest.WebManifest):
    def _get_scoped_app_shortcuts(self, app_id):
        if app_id == "industry_fsm":
            return [
                {
                    "name": request.env._("New task"),
                    "url": "/scoped_app/field-service/new",
                },
                {
                    "name": request.env._("My Tasks"),
                    "url": "/scoped_app/field-service",
                },
                {
                    "name": request.env._("My Calendar"),
                    "url": "/scoped_app/field-service?view_type=calendar",
                },
            ]
        return super()._get_scoped_app_shortcuts(app_id)

from odoo import http
from odoo.http import request
from odoo.tools import file_open
from odoo.tools.image import image_process

from odoo.addons.web.controllers import webmanifest

MRP_SHOP_FLOOR_APP_ID = "mrp_shop_floor"


class WebManifest(webmanifest.WebManifest):
    def _get_scoped_app_icons(self, app_id):
        if app_id == MRP_SHOP_FLOOR_APP_ID:
            return [
                {
                    "src": "/mrp_workorder/static/description/mrp_display_icon.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                }
            ]
        return super()._get_scoped_app_icons(app_id)

    @http.route()
    def scoped_app_icon_png(self, app_id):
        if app_id == MRP_SHOP_FLOOR_APP_ID:
            with file_open(
                "mrp_workorder/static/description/mrp_display_icon.png", "rb"
            ) as file:
                image = image_process(
                    file.read(),
                    size=(180, 180),
                    expand=True,
                    colorize=(255, 255, 255),
                    padding=16,
                )
            return request.prepare_response(
                image, headers=[("Content-Type", "image/png")]
            )
        return super().scoped_app_icon_png(app_id)

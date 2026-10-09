import werkzeug

from odoo import http
from odoo.http import request


class PosOrderTrackingDisplay(http.Controller):
    @http.route("/pos-order-tracking/", auth="public", type="http", website=True)
    def pos_order_tracking_display(self, access_token):  # noqa: E8539  device: a device's or a kiosk's credential, presented by a program
        preparation_display_sudo = (
            request.env["pos.prep.display"].sudo()._from_tracking_token(access_token)
        )
        if not preparation_display_sudo:
            raise werkzeug.exceptions.NotFound
        return request.render(
            "pos_order_tracking_display.index",
            {
                "session_info": {
                    **request.env["ir.http"].get_frontend_session_info(),
                    "preparation_display": {
                        **preparation_display_sudo.read(
                            ["auto_clear", "clear_time_interval"]
                        )[0],
                        "bus_channel": preparation_display_sudo._pos_bus_channel(
                            "order_tracking"
                        ),
                    },
                    "initial_data": preparation_display_sudo._get_pos_orders(),
                    "db": request.env.cr.dbname,
                },
            },
        )

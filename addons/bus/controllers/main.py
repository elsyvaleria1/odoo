from werkzeug.exceptions import BadRequest

from odoo.http import Controller, request, route


class BusController(Controller):
    @route("/bus/has_missed_notifications", type="jsonrpc", auth="public")
    def has_missed_notifications(self, last_notification_id) -> bool:
        if not isinstance(last_notification_id, int) or isinstance(
            last_notification_id, bool
        ):
            raise BadRequest("last_notification_id must be an integer")
        request.env.cr.execute(
            "SELECT NOT EXISTS(SELECT 1 FROM bus_bus WHERE id = %s)",
            [last_notification_id],
        )
        return bool(request.env.cr.fetchone()[0])

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class CalendarSyncController(http.Controller):
    @http.route("/calendar_sync/<string:code>/sync_data", type="jsonrpc", auth="user")
    def calendar_sync_data(self, code, model, **kw):
        """Synchronize the user's calendar with `code`'s provider, as the
        calendar view asks: need_config_from_admin, need_auth (with the URL that
        authorizes it), sync_stopped / sync_paused, need_refresh, no_new_event."""
        if model != "calendar.event":
            return {"status": "success"}
        Account = request.env["calendar.sync.account"]
        if code not in Account._calendar_sync_providers():
            raise NotFound
        user = request.env.user
        provider = Account._provider(code)
        if not Account._has_client(code):
            action = ""
            if user.has_group("base.group_erp_manager"):
                action = request.env.ref("web.action_general_configuration").id
            return {"status": "need_config_from_admin", "url": "", "action": action}
        if not user._calendar_sync_connection(code):
            connection = request.env["integration.connection"]._personal(
                request.env.ref(provider.service), user, scope=provider.scope
            )
            return {
                "status": "need_auth",
                "url": connection._oauth_authorize_url(kw.get("fromurl")),
            }
        need_refresh = user.sudo()._calendar_sync_run(code)
        status = user._calendar_sync_status(code)
        if not need_refresh and status != "sync_active":
            return {"status": status, "url": ""}
        return {"status": "need_refresh" if need_refresh else "no_new_event", "url": ""}

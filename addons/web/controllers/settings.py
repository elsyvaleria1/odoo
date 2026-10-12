from typing import Any

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class BaseSetup(http.Controller):
    @http.route("/base_setup/data", type="jsonrpc", auth="user", readonly=True)
    def base_setup_data(self, **kw: Any) -> dict[str, Any]:
        if _debug.lifecycle.enabled:
            _debug.lifecycle("base_setup_data", ignored=sorted(kw))
        if not request.env.user.has_group("base.group_erp_manager"):
            _debug.logic("base_setup_data_refused", reason="not_erp_manager")
            raise AccessError(request.env._("Access Denied"))

        Users = request.env["res.users"]
        internal = [("share", "=", False)]
        with _debug.perf("base_setup_data_users_count", cr=request.env.cr):
            active_count = Users.search_count(internal)
            pending = Users.search(
                [*internal, ("log_ids", "=", False)], order="id desc"
            )
        pending_users = [(user.id, user.login) for user in pending[:10]]
        _debug.perf.count(
            "base_setup_data_users",
            active=active_count,
            pending=len(pending),
            sample=len(pending_users),
        )
        return {
            "active_users": active_count,
            "pending_count": len(pending),
            "pending_users": pending_users,
            "action_pending_users": pending[:10]._action_show(),
        }

    @http.route("/base_setup/demo_active", type="jsonrpc", auth="user", readonly=True)
    def base_setup_is_demo(self, **kwargs: Any) -> bool:
        demo = bool(
            request.env["ir.module.module"].search_count([("demo", "=", True)], limit=1)
        )
        _debug.logic("base_setup_demo_active", demo=demo)
        return demo

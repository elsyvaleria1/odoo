from odoo.exceptions import AccessError
from odoo.http import Controller, request, route
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class View(Controller):
    @route("/web/view/edit_custom", type="jsonrpc", auth="user")
    def edit_custom(self, custom_id: int, arch: str) -> dict[str, bool]:
        _debug.lifecycle("custom_view_edit", custom_view=custom_id, arch_len=len(arch))
        custom_view = request.env["ir.ui.view.custom"].sudo().browse(custom_id)
        if custom_view.user_id != request.env.user:
            _debug.logic(
                "custom_view_edit_refused",
                custom_view=custom_id,
                owner_uid=custom_view.user_id.id,
                uid=request.env.uid,
            )
            raise AccessError(
                request.env._(
                    "Custom view %(view)s does not belong to user %(user)s",
                    view=custom_id,
                    user=request.env.user.login,
                )
            )
        with _debug.perf(
            "custom_view_arch_write", cr=request.env.cr, custom_view=custom_id
        ):
            custom_view.write({"arch": arch})
        return {"result": True}

from odoo import models
from odoo.http import root

from odoo.addons.bus.websocket import wsrequest


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _update_mail_presence(self, inactivity_period) -> None:
        self.env["ir.http"]._set_session_inactivity(
            wsrequest.session, inactivity_period
        )
        super()._update_mail_presence(inactivity_period)

    def _on_websocket_closed(self, cookies):
        session_id = cookies.get("session_id")
        if self.env.user and session_id:
            session = root.session_store.get(session_id)
            if not session.is_new:
                self.env["ir.http"]._set_session_inactivity(session, force=True)
        super()._on_websocket_closed(cookies)

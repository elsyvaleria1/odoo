from typing import Any

from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardMailMessageSendPortalLink(models.TransientModel):
    _inherit = "wizard.mail.message.send.portal.link"

    def action_send_mail(self) -> dict[str, Any]:
        result = super().action_send_mail()

        if self.res_model == "project.task":
            _debug.pipeline(
                "portal_share_subscribing", task=self.res_id, partners=self.partner_ids
            )
            self.resource_ref.message_subscribe(partner_ids=self.partner_ids.ids)

        return result

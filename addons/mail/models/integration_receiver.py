from odoo import models

from ..tools.inbound_delivery import INBOUND_MAIL_MAX_BYTES, INBOUND_MAIL_PURPOSE
from odoo.addons.integration.tools.admission import Admission


class IntegrationReceiver(models.Model):
    _inherit = "integration.receiver"

    def _is_inbound_mail_receiver(self) -> bool:
        self.check_singleton()
        return (
            self.res_model == "fetchmail.server"
            and self.res_purpose == INBOUND_MAIL_PURPOSE
        )

    def _inbound_event_id(
        self, admission: Admission, event_type: str | None
    ) -> str | None:
        if self._is_inbound_mail_receiver():
            return admission.payload_hash
        return super()._inbound_event_id(admission, event_type)

    def _inbound_payload_logged(self, event_type: str | None) -> bool:
        if self._is_inbound_mail_receiver():
            return False
        return super()._inbound_payload_logged(event_type)

    def _inbound_max_payload_size(self) -> int:
        if self._is_inbound_mail_receiver():
            return max(super()._inbound_max_payload_size(), INBOUND_MAIL_MAX_BYTES)
        return super()._inbound_max_payload_size()

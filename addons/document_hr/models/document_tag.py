from odoo import api, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsTag(models.Model):
    _inherit = "document.tag"

    @api.ondelete(at_uninstall=False)
    def _unlink_except_contract_signature_tag(self) -> None:
        tag = self.env.ref(
            "document_hr.document_tag_signature_request", raise_if_not_found=False
        )
        if tag and tag in self:
            _debug.logic("tag_unlink_refused", reason="contract_signature", tags=self)
            raise UserError(
                self.env._(
                    "You cannot delete this tag as it is used to link employee contracts and signatures."
                )
            )

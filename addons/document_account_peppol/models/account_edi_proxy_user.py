from odoo import models
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class Account_Edi_Proxy_ClientUser(models.Model):
    _inherit = "account_edi_proxy_client.user"

    def _peppol_import_invoice(
        self, attachment, peppol_state, uuid, journal=None
    ) -> dict:
        if self.company_id.peppol_reception_mode == "documents":
            _debug.pipeline("peppol_received", by="documents", company=self.company_id)
            document = self.env["document.document"].create(
                {
                    "attachment_id": attachment.id,
                    "folder_id": self.company_id.documents_account_peppol_folder_id.id,
                    "tag_ids": [
                        Command.set(
                            self.company_id.documents_account_peppol_tag_ids.ids
                        )
                    ],
                }
            )
            document._message_log(
                body=self.env._(
                    "Peppol document (UUID: %(uuid)s) has been received successfully.",
                    uuid=uuid,
                ),
            )
            _debug.lifecycle("peppol_document_created", document=document)
            return {"uuid": uuid}
        _debug.pipeline("peppol_received", by="journal", company=self.company_id)
        return super()._peppol_import_invoice(
            attachment, peppol_state, uuid, journal=journal
        )

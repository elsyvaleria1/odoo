from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SignDocument(models.Model):
    _name = "sign.document"
    _inherit = ["sign.document", "mixin.documents.unlink"]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            attachment_id = vals.get("attachment_id")
            attachment = self.env["ir.attachment"].browse(attachment_id)

            if attachment:
                if attachment.res_model and attachment.res_model != "document.document":
                    _debug.logic(
                        "sign_attachment", by="copied", res_model=attachment.res_model
                    )
                    vals["attachment_id"] = attachment.copy().id
                else:
                    _debug.logic("sign_attachment", by="detached")
                    attachment.write({"res_model": False, "res_id": 0})

        records = super().create(vals_list)

        for record in records:
            if record.attachment_id:
                record.attachment_id.write(
                    {"res_model": record._name, "res_id": record.id}
                )

        return records

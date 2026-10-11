from odoo import models


class MixinMailThread(models.AbstractModel):
    _inherit = "mixin.mail.thread"

    def _mail_get_partner_fields(self, introspect_fields=False):
        fields = super()._mail_get_partner_fields(introspect_fields=introspect_fields)
        field = self._fields.get("x_studio_partner_id")
        if field and field.type == "many2one" and field.comodel_name == "res.partner":
            fields.append("x_studio_partner_id")
        return fields

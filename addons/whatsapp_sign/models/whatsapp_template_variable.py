from odoo import models


class WhatsappTemplateVariable(models.Model):
    _inherit = "whatsapp.template.variable"

    def _find_value_from_field_chain(self, record):
        self.check_singleton()
        if (
            record._name == "sign.request.item"
            and self.field_name in record._get_fields_sudo_access()
        ):
            return self._resolve_field_path_value(record.sudo(True))
        else:
            return super()._find_value_from_field_chain(record)

from odoo import api, models

from odoo.addons.base_import.models.base_import import FIELDS_RECURSION_LIMIT


class Base_ImportImport(models.TransientModel):
    _inherit = "base_import.import"

    @api.model
    def get_fields_tree(self, model, depth=FIELDS_RECURSION_LIMIT):
        if model != "account.move.line":
            return super().get_fields_tree(model, depth=depth)
        fields_list = super().get_fields_tree(model, depth=depth)
        Model = self.env[model]
        model_fields = Model.fields_get()
        add_fields = []
        for field in ("move_id", "journal_id", "date"):
            field_value = {
                "id": field,
                "name": field,
                "string": model_fields[field]["string"],
                "required": bool(model_fields[field].get("required")),
                "fields": [],
                "type": model_fields[field]["type"],
                "model_name": model,
            }
            add_fields.append(field_value)
        fields_list.extend(add_fields)

        return fields_list

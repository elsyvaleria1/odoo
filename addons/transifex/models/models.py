from odoo import models


class Base(models.AbstractModel):
    _inherit = "base"

    def get_field_translations(self, field_name, langs=None):
        translations, context = super().get_field_translations(field_name, langs=langs)
        external_id = self.get_external_id().get(self.id)
        if not external_id:
            return translations, context

        module = external_id.split(".")[0]
        if module not in self.pool.loaded_modules:
            return translations, context

        for translation in translations:
            translation["module"] = module
        self.env["transifex.translation"]._update_transifex_url(translations)
        return translations, context

from odoo import models


class Base(models.AbstractModel):
    _inherit = "base"

    def _can_return_content(self, field_name=None, access_token=None) -> bool:
        if (
            "website_published" in self._fields
            and field_name in self._fields
            and self._fields[field_name].access_classes is None
            and self.sudo().website_published
        ):
            return True
        return super()._can_return_content(field_name, access_token)

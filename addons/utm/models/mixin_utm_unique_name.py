from typing import TYPE_CHECKING, Self, cast

from odoo import api, models
from odoo.api import ValuesType

if TYPE_CHECKING:
    from .mixin_utm import MixinUtm


class MixinUtmUniqueName(models.AbstractModel):
    _name = "mixin.utm.unique.name"
    _description = "UTM unique name on creation"

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        new_names = cast("MixinUtm", self.env["mixin.utm"])._get_unique_names(
            self._name, [vals.get("name") for vals in vals_list]
        )
        for vals, new_name in zip(vals_list, new_names, strict=True):
            vals["name"] = new_name
        return super().create(vals_list)

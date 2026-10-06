from odoo import models
from odoo.api import ValuesType
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MixinProjectPm(models.AbstractModel):
    _name = "mixin.project.pm"
    _description = "Project PM Record Mixin"

    def copy_data(self, default: ValuesType | None = None) -> list[ValuesType]:
        vals_list = super().copy_data(default=default)
        _debug.lifecycle("copy_data", records=self, default=sorted(default or {}))
        return [
            dict(vals, name=self.env._("%s (copy)", record.name))
            for record, vals in zip(self, vals_list, strict=True)
        ]

    def copy_translations(self, new, excluded=()) -> None:
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

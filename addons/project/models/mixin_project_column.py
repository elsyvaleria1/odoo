from odoo import fields, models
from odoo.api import ValuesType
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MixinProjectColumn(models.AbstractModel):
    _name = "mixin.project.column"
    _description = "Project Kanban Column"
    _order = "sequence, id"

    active = fields.Boolean(
        export_string_translation=False,
        default=True,
    )
    sequence = fields.Integer(
        export_string_translation=False,
        default=1,
    )
    name = fields.Char(
        translate=True,
        required=True,
    )
    fold = fields.Boolean(string="Folded")
    color = fields.Integer(export_string_translation=False)

    def copy_data(self, default: ValuesType | None = None) -> list[ValuesType]:
        vals_list = super().copy_data(default=default)
        _debug.lifecycle("copy_data", records=self, default=sorted(default or {}))
        if default and "name" in default:
            return vals_list
        return [
            dict(vals, name=self.env._("%s (copy)", record.name))
            for record, vals in zip(self, vals_list, strict=True)
        ]

    def copy_translations(self, new, excluded=()) -> None:
        if new.name != self.env._("%s (copy)", self.name):
            super().copy_translations(new, excluded=excluded)
            return
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

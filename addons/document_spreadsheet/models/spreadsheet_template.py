from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SpreadsheetTemplate(models.Model):
    _name = "spreadsheet.template"
    _inherit = ["mixin.spreadsheet"]
    _description = "Spreadsheet Template"
    _order = "sequence"

    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=100)
    file_name = fields.Char(compute="_compute_file_name")

    @api.depends("name")
    def _compute_file_name(self) -> None:
        for template in self:
            template.file_name = f"{template.name}.osheet.json"

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        for template, vals in zip(self, vals_list, strict=False):
            vals["name"] = default.get("name", self.env._("%s (copy)", template.name))
        return vals_list

    def copy_translations(self, new, excluded=()) -> None:
        # ``copy_data`` renames ``name`` in the duplicating user's language
        # only; without this the copy would keep the source record's exact
        # ``name`` in every other language.
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

    def action_edit_template(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.client",
            "tag": "action_view_template",
            "params": {
                "spreadsheet_id": self.id,
            },
        }

    def action_create_spreadsheet(self, document_vals=None) -> dict:
        if document_vals is None:
            document_vals = {}
        self.check_singleton()
        spreadsheet = self.env["document.document"].create(
            {
                "name": self.name,
                "mimetype": "application/o-spreadsheet",
                "handler": "spreadsheet",
                "spreadsheet_data": self.spreadsheet_data,
                **document_vals,
            }
        )
        spreadsheet.spreadsheet_snapshot = self.spreadsheet_snapshot
        self._copy_revisions_to(spreadsheet)
        spreadsheet._remove_comments_from_data()

        update_locale_command = {
            "type": "UPDATE_LOCALE",
            "locale": self.env["res.lang"]._get_user_spreadsheet_locale(),
        }
        spreadsheet._dispatch_command(update_locale_command)
        _debug.lifecycle(
            "spreadsheet_created_from_template",
            template=self,
            spreadsheet=spreadsheet,
            locale=update_locale_command["locale"]["code"],
        )

        return {
            "type": "ir.actions.client",
            "tag": "action_view_spreadsheet",
            "params": {
                "spreadsheet_id": spreadsheet.id,
            },
        }

    def action_view_spreadsheet(self):
        self.check_singleton()
        return {
            "type": "ir.actions.client",
            "tag": "action_view_template",
            "params": {
                "spreadsheet_id": self.id,
            },
        }

from typing import Any

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardProjectColumnDelete(models.TransientModel):
    _name = "wizard.project.column.delete"
    _description = "Delete Project Kanban Columns"

    res_model = fields.Selection(
        selection="_selection_res_model",
        string="Column Model",
        required=True,
    )
    res_ids = fields.Json(
        string="Columns",
        export_string_translation=False,
    )
    project_ids = fields.Many2many(
        comodel_name="project.project",
        string="Projects",
        export_string_translation=False,
        compute="_compute_project_ids",
    )
    count_member = fields.Integer(
        string="Number of Records",
        export_string_translation=False,
        compute="_compute_count_member",
    )
    is_columns_active = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_columns_active",
    )
    message = fields.Text(
        export_string_translation=False,
        compute="_compute_message",
    )

    @api.constrains("res_model", "res_ids")
    def _check_columns(self) -> None:
        models_allowed = {name for name, _label in self._selection_res_model()}
        for wizard in self:
            ids = wizard.res_ids or []
            if wizard.res_model not in models_allowed:
                raise ValidationError(
                    self.env._(
                        "%(model)s is not a project column this wizard can delete.",
                        model=wizard.res_model,
                    )
                )
            if not isinstance(ids, list) or not all(
                type(column_id) is int for column_id in ids
            ):
                raise ValidationError(
                    self.env._("The columns to delete must be a list of record ids.")
                )

    @api.depends("res_model", "res_ids")
    def _compute_project_ids(self) -> None:
        for wizard in self:
            wizard.project_ids = wizard._get_columns()._get_sharing_projects()

    @api.depends("res_model", "res_ids")
    def _compute_count_member(self) -> None:
        for wizard in self:
            columns = wizard._get_columns()
            wizard.count_member = columns._get_member_count() if columns else 0

    @api.depends("res_model", "res_ids")
    def _compute_is_columns_active(self) -> None:
        for wizard in self:
            wizard.is_columns_active = all(wizard._get_columns().mapped("active"))

    @api.depends("count_member", "res_model", "res_ids")
    def _compute_message(self) -> None:
        for wizard in self:
            columns = wizard._get_columns()
            wizard.message = (
                columns._get_delete_message(wizard.count_member) if columns else False
            )

    def _selection_res_model(self) -> list[tuple[str, str]]:
        Container = self.pool["mixin.project.column.container"]
        return [
            (name, self.env[name]._description)
            for name in sorted(self.pool)
            if isinstance(self.env[name], Container) and not self.env[name]._abstract
        ]

    def action_archive(self) -> dict[str, Any]:
        columns = self._get_columns()
        _debug.lifecycle("columns_archived", columns=columns)
        columns.action_archive()
        return self._prepare_action_redirect()

    def action_unlink(self) -> dict[str, Any]:
        columns = self._get_columns()
        _debug.lifecycle("columns_unlinked", columns=columns)
        columns.unlink()
        return self._prepare_action_redirect()

    def _get_columns(self) -> models.BaseModel:
        self.check_singleton()
        if not self.res_model:
            return self.env["mixin.project.column.container"]
        return self.env[self.res_model].browse(self.res_ids or [])

    def _prepare_action_redirect(self) -> dict[str, Any]:
        if not self.env.context.get("stage_view"):
            return {
                "type": "ir.actions.act_window_close",
                "infos": {"success": True},
            }
        # opened from the column's own views, whose record may be gone: reopen
        # the column list instead of reloading it
        Actions = self.env["ir.actions.actions"]
        action = Actions._get_action_dict_by_xml_id(
            self.env[self.res_model]._column_action
        )
        action["context"] = dict(
            Actions._eval_action_context(action.get("context")),
            active_test=True,
        )
        action["target"] = "main"
        return action

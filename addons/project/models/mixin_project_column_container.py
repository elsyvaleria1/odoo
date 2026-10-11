from typing import Any, NamedTuple

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL
from odoo.tools.translate import LazyGettext

_debug = DebugLog(__name__)


class ColumnDeleteTexts(NamedTuple):
    title: LazyGettext
    confirm: LazyGettext
    archive: LazyGettext
    blocked: LazyGettext


class MixinProjectColumnContainer(models.AbstractModel):
    _name = "mixin.project.column.container"
    _description = "Project Kanban Column Holding Records"
    _inherit = ["mixin.project.column"]

    _member_model = ""
    _member_field = ""
    _column_action = ""
    _delete_texts: ColumnDeleteTexts

    mail_template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Email Template",
        domain=lambda self: self._domain_mail_template_id(),
    )
    is_archive_recorded = fields.Boolean(
        export_string_translation=False,
        copy=False,
    )

    def _domain_mail_template_id(self) -> list:
        return [("model", "=", self._member_model)]

    @api.constrains("mail_template_id")
    def _check_mail_template_model(self) -> None:
        member_model = self.env["ir.model"]._get(self._member_model)
        for column in self:
            template = column.mail_template_id
            if template and template.model != self._member_model:
                raise ValidationError(
                    self.env._(
                        "The email template %(template)s is defined on %(model)s, but "
                        "%(column)s sends it about a record of %(member_model)s. "
                        "Choose a template whose model is %(member_model)s.",
                        template=template.display_name,
                        model=template.model,
                        column=column.display_name,
                        member_model=member_model.name,
                    )
                )

    def write(self, vals: dict) -> bool:
        if "active" not in vals:
            return super().write(vals)
        restoring = bool(vals["active"])
        columns = self.filtered(lambda column: column.active != restoring)
        if not columns:
            return super().write(vals)
        members = (
            columns._get_members_to_restore()
            if restoring
            else columns._get_members_to_archive()
        )
        if not self.env.su:
            columns._check_archive_reach(
                members,
                hidden=columns._count_reached_members(restoring) - len(members),
            )
        if not restoring:
            columns._update_members_archived(members)
            return super().write(vals)
        res = super().write(vals)
        columns._update_members_restored(members)
        columns.write({"archived_member_ids": [Command.clear()]})
        return res

    def unlink(self) -> bool:
        if not self.env.su:
            self._check_archive_reach(self.env[self._member_model], hidden=0)
        return super().unlink()

    def action_open_delete_wizard(self, stage_view: bool = False) -> dict[str, Any]:
        _debug.lifecycle("delete_wizard_opened", columns=self, stage_view=stage_view)
        wizard = self.env["wizard.project.column.delete"].create(
            {"res_model": self._name, "res_ids": self.ids}
        )
        return {
            "name": str(self._delete_texts.title),
            "view_mode": "form",
            "res_model": wizard._name,
            "views": [(False, "form")],
            "type": "ir.actions.act_window",
            "res_id": wizard.id,
            "target": "new",
            "context": dict(self.env.context, stage_view=stage_view),
        }

    def _count_reached_members(self, restoring: bool) -> int:
        Member = self.env[self._member_model]
        Member.flush_model([self._member_field, "active"])
        table = SQL.identifier(Member._table)
        column = SQL.identifier(self._member_field)
        if not restoring:
            query = SQL(
                "SELECT count(*) FROM %s WHERE %s = ANY(%s) AND active",
                table,
                column,
                self.ids,
            )
            return self.env.execute_query(query)[0][0]
        self.flush_recordset(["archived_member_ids", "is_archive_recorded"])
        recorded = self.filtered("is_archive_recorded")
        legacy = self - recorded
        count = 0
        if legacy:
            count += self.env.execute_query(
                SQL(
                    "SELECT count(*) FROM %s WHERE %s = ANY(%s) AND NOT active",
                    table,
                    column,
                    legacy.ids,
                )
            )[0][0]
        if recorded:
            relation = self._fields["archived_member_ids"]
            count += self.env.execute_query(
                SQL(
                    "SELECT count(*) FROM %s rel JOIN %s member"
                    " ON member.id = rel.%s"
                    " WHERE rel.%s = ANY(%s) AND NOT member.active"
                    " AND member.%s = rel.%s",
                    SQL.identifier(relation.relation),
                    table,
                    SQL.identifier(relation.column2),
                    SQL.identifier(relation.column1),
                    recorded.ids,
                    column,
                    SQL.identifier(relation.column1),
                )
            )[0][0]
        return count

    def _count_hidden_projects(self) -> int:
        return 0

    def _get_delete_message(self, count_member: int) -> str:
        texts = self._delete_texts
        if not count_member:
            return str(texts.confirm)
        if all(self.mapped("active")):
            return str(texts.archive)
        return str(texts.blocked)

    def _get_member_count(self) -> int:
        return (
            self.env[self._member_model]
            .with_context(active_test=False)
            .search_count([(self._member_field, "in", self.ids)])
        )

    def _get_members_to_archive(self) -> models.BaseModel:
        return (
            self.env[self._member_model]
            .with_context(active_test=True)
            .search([(self._member_field, "in", self.ids)])
        )

    def _get_members_to_restore(self) -> models.BaseModel:
        recorded = self.filtered("is_archive_recorded")
        members = recorded.archived_member_ids.filtered(
            lambda member: not member.active and member[self._member_field] in recorded
        )
        legacy = self - recorded
        if legacy:
            members |= (
                self.env[self._member_model]
                .with_context(active_test=False)
                .search(
                    [(self._member_field, "in", legacy.ids), ("active", "=", False)]
                )
            )
        _debug.logic(
            "members_to_restore",
            columns=self,
            recorded=recorded,
            legacy=legacy,
            members=members,
        )
        return members

    def _get_projects_out_of_reach(self, members: models.BaseModel) -> models.BaseModel:
        return self.env["project.project"]

    def _get_sharing_projects(self) -> models.BaseModel:
        return self.env["project.project"]

    def _check_archive_reach(self, members: models.BaseModel, hidden: int) -> None:
        user_env = self.env(su=False)
        unwritable = members - members.with_env(user_env)._filtered_access("write")
        projects = self._get_projects_out_of_reach(members)
        hidden += self._count_hidden_projects()
        _debug.logic(
            "archive_reach_checked",
            columns=self,
            members=members,
            unwritable=unwritable,
            projects=projects,
            hidden=hidden,
        )
        if unwritable or projects or hidden:
            raise UserError(
                self.env._(
                    "You cannot archive, restore or delete %(columns)s: it is "
                    "shared with projects you cannot modify. Ask a project manager "
                    "to do it.",
                    columns=", ".join(self.with_env(user_env).mapped("display_name")),
                )
            )

    def _update_members_archived(self, members: models.BaseModel) -> None:
        if not self:
            return
        _debug.pipeline("members_archived", columns=self, members=members)
        self.is_archive_recorded = True
        for column, column_members in members.grouped(self._member_field).items():
            column.archived_member_ids = [Command.link(m.id) for m in column_members]
        members.write({"active": False})

    def _update_members_restored(self, members: models.BaseModel) -> None:
        if not self:
            return
        _debug.pipeline("members_restored", columns=self, restored=members)
        self.is_archive_recorded = False
        members.write({"active": True})

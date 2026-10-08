from odoo import Command, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)


class MixinProjectPm(models.AbstractModel):
    _name = "mixin.project.pm"
    _description = "Project Kanban Column"
    _order = "sequence, id"

    _member_model: str | None = None
    _member_field: str | None = None

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

    def write(self, vals: ValuesType) -> bool:
        if "active" not in vals or not self._member_field:
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
        if self._member_field and not self.env.su:
            self._check_archive_reach(self.env[self._member_model], hidden=0)
        return super().unlink()

    def _count_reached_members(self, restoring: bool) -> int:
        # every member the cascade would reach, read past the user's rules: a
        # member the user cannot see must stop the archive, not slip through it
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

    def _get_member_count(self) -> int:
        return (
            self.env[self._member_model]
            .with_context(active_test=False)
            .search_count([(self._member_field, "in", self.ids)])
        )

    def _get_members_to_archive(self) -> models.BaseModel:
        return self.env[self._member_model].search(
            [(self._member_field, "in", self.ids)]
        )

    def _get_members_to_restore(self) -> models.BaseModel:
        recorded = self.filtered("is_archive_recorded")
        members = recorded.archived_member_ids.filtered(
            lambda member: not member.active and member[self._member_field] in recorded
        )
        legacy = self - recorded
        if legacy:
            # archived before the cascade was recorded: restore what the column
            # holds, as the unarchive wizard of that time did
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

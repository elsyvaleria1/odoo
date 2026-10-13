from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MixinAccountMergeLine(models.AbstractModel):
    _name = "mixin.account.merge.line"
    _description = "Accounting Merge Wizard Line Mixin"

    _merge_record_field = None
    _merge_record_display_type = None
    _merge_record_hashed_field = None

    grouping_key = fields.Char()
    sequence = fields.Integer()
    is_selected = fields.Boolean()
    info = fields.Char(
        compute="_compute_info",
        help="Contains either the section name or error message, depending on the line type.",
    )

    def _get_merge_record(self):
        return self[self._merge_record_field]

    def _get_merge_section_name(self):
        raise NotImplementedError

    def _get_mergeable_groups(self):
        return (
            self.filtered(
                lambda line: (
                    line.display_type == self._merge_record_display_type
                    and line.is_selected
                    and not line.info
                )
            )
            .grouped("grouping_key")
            .values()
        )

    def _compute_info(self) -> None:
        for line in self.filtered(lambda l: l.display_type == "line_section"):
            line.info = line._get_merge_section_name()
        for group in (
            self.filtered(lambda l: l.display_type == self._merge_record_display_type)
            .grouped(lambda l: (l.wizard_id, l.grouping_key))
            .values()
        ):
            group.info = False
            group._update_info_conflicts()

    def _update_info_conflicts(self) -> None:
        self._update_info_company_conflict()
        self._update_info_hashed_moves_conflict()

    def _update_info_company_conflict(self) -> None:
        companies_seen = self.env["res.company"]
        owner_by_company = {}
        for line in self:
            if not line.is_selected or line.info:
                continue
            if shared_companies := (line.company_ids & companies_seen):
                _debug.logic(
                    "merge_company_conflict",
                    wizard_line=line,
                    companies=shared_companies,
                )
                line.info = self.env._(
                    "Belongs to the same company as %s.",
                    owner_by_company[shared_companies[0]].display_name,
                )
            else:
                companies_seen |= line.company_ids
                for company in line.company_ids:
                    owner_by_company.setdefault(company, line._get_merge_record())

    def _update_info_hashed_moves_conflict(self) -> None:
        record_to_merge_into = None
        for line in self:
            if (
                not line.is_selected
                or line.info
                or not line[self._merge_record_hashed_field]
            ):
                continue
            if record_to_merge_into is None:
                record_to_merge_into = line._get_merge_record()
            else:
                line.info = self.env._(
                    "Contains hashed entries, but %s also has hashed entries.",
                    record_to_merge_into.display_name,
                )

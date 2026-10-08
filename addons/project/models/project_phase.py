from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import LazyTranslate

from .mixin_project_column_container import ColumnDeleteTexts

_debug = DebugLog(__name__)
_lt = LazyTranslate(__name__)


class ProjectPhase(models.Model):
    _name = "project.phase"
    _description = "Project Phase"
    _inherit = ["mixin.project.column.container"]

    _member_model = "project.project"
    _member_field = "phase_id"
    _column_action = "project.project_phase_configure"
    _delete_texts = ColumnDeleteTexts(
        title=_lt("Delete Phase"),
        confirm=_lt("Are you sure you want to delete these phases?"),
        archive=_lt(
            "You cannot delete phases containing projects. You can either archive "
            "them or first delete all of their projects."
        ),
        blocked=_lt(
            "You cannot delete phases containing projects. You should first delete "
            "all of their projects."
        ),
    )

    sequence = fields.Integer(default=50)
    mail_template_id = fields.Many2one(
        help="Email sent automatically when a project enters this phase.",
    )
    fold = fields.Boolean(
        help="Folded phases are shown collapsed in Kanban and List views. "
        "Projects in a folded phase are considered closed.",
    )
    company_id = fields.Many2one(comodel_name="res.company")
    archived_member_ids = fields.Many2many(
        comodel_name="project.project",
        relation="project_phase_archived_project_rel",
        column1="phase_id",
        column2="project_id",
        string="Projects Archived With the Phase",
        export_string_translation=False,
        copy=False,
        context={"active_test": False},
    )

    @_debug.perf.timed
    def write(self, vals: dict) -> bool:
        _debug.lifecycle("write", phases=self, keys=sorted(vals))
        if vals.get("company_id"):
            project = self.env["project.project"].search(
                [
                    "&",
                    ("phase_id", "in", self.ids),
                    ("company_id", "!=", vals["company_id"]),
                ],
                limit=1,
            )
            if project:
                company = self.env["res.company"].browse(vals["company_id"])
                raise UserError(
                    self.env._(
                        "You cannot switch this phase to %(company_name)s because it "
                        "currently includes projects linked to %(project_company_name)s.",
                        company_name=company.name,
                        project_company_name=project.company_id.name
                        or self.env._("no company"),
                    )
                )
        return super().write(vals)

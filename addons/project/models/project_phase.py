from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProjectPhase(models.Model):
    _name = "project.phase"
    _description = "Project Phase"
    _inherit = ["mixin.project.pm"]

    _member_model = "project.project"
    _member_field = "phase_id"

    sequence = fields.Integer(default=50)
    mail_template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Email Template",
        domain=[("model", "=", "project.project")],
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
    is_archive_recorded = fields.Boolean(
        export_string_translation=False,
        copy=False,
    )

    @api.constrains("mail_template_id")
    def _check_mail_template_model(self) -> None:
        for phase in self:
            template = phase.mail_template_id
            if template and template.model != "project.project":
                raise ValidationError(
                    self.env._(
                        "The email template %(template)s is defined on %(model)s, but a "
                        "phase email is sent about a project. Choose a template whose "
                        "model is Project.",
                        template=template.display_name,
                        model=template.model,
                    )
                )

    def action_open_delete_wizard(self, stage_view: bool = False) -> dict[str, Any]:
        _debug.lifecycle("delete_wizard_opened", phases=self, stage_view=stage_view)
        wizard = self.env["wizard.project.phase.delete"].create({"phase_ids": self.ids})
        context = dict(self.env.context, stage_view=stage_view)
        return {
            "name": self.env._("Delete Phase"),
            "view_mode": "form",
            "res_model": "wizard.project.phase.delete",
            "views": [
                (
                    self.env.ref("project.view_project_phase_delete_wizard").id,
                    "form",
                )
            ],
            "type": "ir.actions.act_window",
            "res_id": wizard.id,
            "target": "new",
            "context": context,
        }

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

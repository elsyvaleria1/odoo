from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.base.models.mixin_catalog import name_uniq_index


class ProjectTaskDescriptionTemplate(models.Model):
    _name = "project.task.description.template"
    _inherit = ["mixin.catalog"]
    _description = "Project Task Description Template"
    _order = "sequence, name"

    description = fields.Html(
        translate=True,
        required=True,
    )
    sequence = fields.Integer(
        default=10,
        help="Order of templates in selection lists",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
    )
    project_ids = fields.Many2many(
        comodel_name="project.project",
        string="Projects",
        help="Leave empty to make this template available for all projects",
    )

    _name_src_uniq = name_uniq_index(
        "company_id",
        message="A template with this name already exists for this company.",
    )

    def _violation_for_task(self, task) -> str | None:
        self.check_singleton()
        if (
            task.project_id
            and self.project_ids
            and task.project_id not in self.project_ids
        ):
            return self.env._(
                "The template %(template)s is not available for the "
                "project %(project)s.",
                template=self.name,
                project=task.project_id.display_name,
            )
        if task.company_id and self.company_id and task.company_id != self.company_id:
            return self.env._(
                "The template %(template)s belongs to company %(company)s.",
                template=self.name,
                company=self.company_id.display_name,
            )
        return None

    @api.constrains("project_ids", "company_id")
    def _check_tasks_still_allowed(self) -> None:
        # sudo and active_test: a task the editor cannot read, or an archived
        # one, is left just as broken as any other, and the task-side
        # constraint does not care about either.
        tasks = (
            self.env["project.task"]
            .sudo()
            .with_context(active_test=False)
            .search([("description_template_id", "in", self.ids)])
        )
        for template in self:
            broken = tasks.filtered(
                lambda task, template=template: (
                    task.description_template_id == template
                    and template._violation_for_task(task)
                )
            )
            if broken:
                raise ValidationError(
                    self.env._(
                        "The template %(template)s is still used by "
                        "%(tasks)s, which this change would leave invalid.",
                        template=template.name,
                        tasks=", ".join(broken.mapped("display_name")),
                    )
                )

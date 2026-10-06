from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import is_html_empty


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = "project.task"

    description_template_id = fields.Many2one(
        comodel_name="project.task.description.template",
        domain="['|', ('project_ids', '=', False), ('project_ids', '=', project_id)]",
        check_company=True,
        help="Templates of other companies are not offered here. A task with "
        "no company is offered only company-less templates, while the server "
        "accepts any template on it: such a task belongs to a shared project "
        "and is deliberately not tied to one company's templates.",
    )
    show_apply_template = fields.Boolean(
        string="Show Apply Template Button",
        compute="_compute_show_apply_template",
        store=False,
        help="True when applying the selected template would change the description",
    )

    @api.depends("description_template_id", "description")
    def _compute_show_apply_template(self) -> None:
        for task in self:
            # Only worth offering when applying the template would actually
            # change the description. An empty description is one of those
            # cases: create() does not run the onchange, so a task can hold a
            # template and show none of its body.
            template = task.description_template_id
            task.show_apply_template = bool(
                template
                and not (
                    is_html_empty(task.description)
                    and is_html_empty(template.description)
                )
                and str(task.description or "") != str(template.description or "")
            )

    @api.constrains("description_template_id", "project_id", "company_id")
    def _check_description_template_id(self) -> None:
        for task in self:
            # sudo: the template may belong to a company the writer cannot read,
            # which is precisely one of the cases this constraint rejects.
            template = task.description_template_id.sudo()
            if not template:
                continue
            message = template._violation_for_task(task)
            if message:
                raise ValidationError(message)

    @api.onchange("description_template_id")
    def _onchange_description_template_id(self) -> None:
        if not self.description_template_id:
            return
        # An untouched body still belongs to the template the record was
        # loaded with, so replacing it loses nothing the user wrote. This
        # cannot see a body applied earlier in the same unsaved form, which
        # is what the Apply Template button is left to cover.
        previous = self._origin.description_template_id.description
        untouched = previous and str(self.description or "") == str(previous)
        if is_html_empty(self.description) or untouched:
            self.description = self.description_template_id.description

    @api.onchange("project_id")
    def _onchange_project_id_description_template(self) -> dict | None:
        if (
            self._has_field_access(self._fields["description_template_id"], "write")
            and self.project_id
            and self.description_template_id
            and self.description_template_id.project_ids
            and self.project_id not in self.description_template_id.project_ids
        ):
            dropped = self.description_template_id
            self.description_template_id = False
            # The description is left as it is: the user may have edited it.
            return {
                "warning": {
                    "title": self.env._("Template removed"),
                    "message": self.env._(
                        "The template %(template)s is not available for the "
                        "project %(project)s, so it was removed. The current "
                        "description was left unchanged.",
                        template=dropped.name,
                        project=self.project_id.display_name,
                    ),
                }
            }
        return None

    def action_apply_template(self) -> None:
        self.check_singleton()
        if self.description_template_id:
            self.description = self.description_template_id.description

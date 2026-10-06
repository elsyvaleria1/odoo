from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MailActivityPlanTemplate(models.Model):
    _inherit = "mail.activity.plan.template"

    sign_template_id = fields.Many2one(
        comodel_name="sign.template",
        string="Document to sign",
    )
    employee_role_id = fields.Many2one(
        comodel_name="sign.item.role",
        compute="_compute_employee_role_id",
        store=True,
        readonly=False,
        domain="[('id', 'in', sign_template_responsible_ids)]",
        help="Employee's role on the templates to sign. The same role must be present in all the templates",
    )
    sign_template_responsible_ids = fields.Many2many(
        comodel_name="sign.item.role",
        compute="_compute_responsible_ids",
    )
    responsible_count = fields.Count(count_of="sign_template_responsible_ids")
    is_signature_request = fields.Boolean(compute="_compute_signature_request")

    @api.constrains("activity_type_id", "sign_template_id", "employee_role_id")
    def _check_employee_role_id(self) -> None:
        # The form view enforces this conditionally, but plans built by
        # RPC/import bypass it and would crash the schedule wizard mid-plan.
        for template in self:
            if template.is_signature_request and not template.employee_role_id:
                raise ValidationError(
                    self.env._(
                        "Signature request activity %s needs the employee's"
                        " role on the document to sign.",
                        template.display_name,
                    )
                )

    @api.depends("activity_type_id")
    def _compute_signature_request(self) -> None:
        for template in self:
            template.is_signature_request = (
                template.activity_type_id.category == "sign_request"
            )

    @api.depends("activity_type_id", "sign_template_id.sign_item_ids.responsible_id")
    def _compute_responsible_ids(self) -> None:
        for template in self:
            template.sign_template_responsible_ids = (
                template.is_signature_request
                and template.sign_template_id.sign_item_ids.responsible_id
            )

    @api.depends("sign_template_responsible_ids")
    def _compute_employee_role_id(self) -> None:
        for template in self:
            roles = template.sign_template_responsible_ids._origin
            role = template.employee_role_id._origin
            if role not in roles:
                role = roles if len(roles) == 1 else False
            template.employee_role_id = role

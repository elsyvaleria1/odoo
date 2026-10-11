import logging

from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_date, html_sanitize, is_html_empty

_logger = logging.getLogger(__name__)


class WizardHrAppraisalSend(models.TransientModel):
    _name = "wizard.hr.appraisal.send"
    _inherit = ["mixin.mail.composer"]
    _description = "Request an Appraisal"
    _unrestricted_rendering = True

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        if not set(fields) & {"employee_id", "template_id", "recipient_ids"}:
            return result
        if self.env.context.get("default_appraisal_id"):
            appraisal = self.env["hr.appraisal"].browse(
                self.env.context["default_appraisal_id"]
            )
            template, recipients = self._get_template_and_recipients(appraisal)
            result.update(
                {
                    "template_id": template.id,
                    "recipient_ids": [Command.set(recipients.ids)],
                    "employee_id": appraisal.employee_id.id,
                    "appraisal_id": appraisal.id,
                }
            )
        return result

    @api.model
    def _get_template_and_recipients(self, appraisal) -> tuple:
        employee = appraisal.employee_id
        managers = appraisal.manager_ids
        if self.env.user.employee_id in managers:
            template = self.env.ref(
                "hr_appraisal.mail_template_appraisal_reminder",
                raise_if_not_found=False,
            )
            recipients = self._get_recipients(employee)
        elif employee.user_id == self.env.user:
            template = self.env.ref(
                "hr_appraisal.mail_template_appraisal_request_from_employee",
                raise_if_not_found=False,
            )
            recipients = self._get_recipients(managers)
        else:
            template = self.env.ref(
                "hr_appraisal.mail_template_appraisal_reminder",
                raise_if_not_found=False,
            )
            recipients = self._get_recipients(employee | managers)
        return template, recipients

    @api.model
    def _get_recipients(self, employees):
        employees_with_user = employees.filtered("user_id")
        partners = employees_with_user.user_id.partner_id

        employees_wemail = (employees - employees_with_user).filtered("work_email")
        for employee_partners in employees_wemail._partner_get_or_create_from_emails(
            {emp: [emp.work_email] for emp in employees_wemail}, no_create=False
        ).values():
            partners |= employee_partners
        return partners

    appraisal_id = fields.Many2one(
        comodel_name="hr.appraisal",
        required=True,
    )
    user_body = fields.Html(string="User Contents")
    author_id = fields.Many2one(
        comodel_name="res.partner",
        default=lambda self: self.env.user.partner_id.id,
        required=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Appraisal Employee",
    )
    recipient_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Recipients",
        required=True,
    )

    @api.constrains("template_id", "appraisal_id")
    def _check_template_id(self) -> None:
        for appraisal_request in self.filtered("template_id"):
            template = appraisal_request.template_id
            appraisal = appraisal_request.appraisal_id
            expected_template, _recipients = (
                appraisal_request._get_template_and_recipients(appraisal)
            )
            if template != expected_template:
                raise ValidationError(
                    self.env._(
                        'Appraisal for %(appraisal_title)s should be using template "%(template_name)s" instead of "%(wrong_template_name)s"',
                        appraisal_title=appraisal.display_name,
                        template_name=expected_template.display_name,
                        wrong_template_name=template.display_name,
                    )
                )

    @api.depends("employee_id")
    def _compute_subject(self) -> None:
        for wizard_su in self.filtered(
            lambda w: w.employee_id and w.template_id
        ).sudo():
            appraisal = wizard_su.appraisal_id
            wizard_su.subject = wizard_su.template_id._render_template(
                wizard_su.template_id.subject,
                appraisal._name,
                appraisal.ids,
                engine="inline_template",
                options={"post_process": True},
            )[appraisal.id]

    def _get_appraisal_url(self) -> str:
        self.check_singleton()
        return "/mail/view?model=%s&res_id=%s" % ("hr.appraisal", self.appraisal_id.id)

    @api.depends("template_id", "recipient_ids", "user_body")
    def _compute_body(self) -> None:
        for wizard in self:
            user_body = wizard.user_body
            user_body = (
                user_body
                if not is_html_empty(
                    html_sanitize(user_body, strip_style=True, strip_classes=True)
                )
                else False
            )
            if wizard.template_id:
                ctx = {
                    "employee_to_name": ", ".join(
                        wizard.recipient_ids.sorted("name").mapped("name")
                    ),
                    "author_name": wizard.author_id.name,
                    "author_mail": wizard.author_id.email,
                    "date_close": format_date(self.env, wizard.appraisal_id.date_close),
                    "recipient_users": wizard.recipient_ids.mapped("user_ids"),
                    "url": wizard._get_appraisal_url(),
                    "user_body": user_body,
                    "author_signature": wizard.author_id.user_id.signature,
                    "manager_names": ", ".join(
                        wizard.appraisal_id.manager_ids.mapped("name")
                    ),
                }
                appraisal = wizard.appraisal_id
                wizard.body = (
                    self.with_context(ctx)
                    .sudo()
                    ._render_template(
                        wizard.template_id.body_html,
                        appraisal._name,
                        appraisal.ids,
                        engine="qweb",
                        options={"post_process": False},
                    )[appraisal.id]
                )
            elif not wizard.body:
                wizard.body = ""

    def _compute_can_edit_body(self) -> None:
        for record in self:
            record.can_edit_body = True

    @api.depends("subject")
    def _compute_render_model(self) -> None:
        self.render_model = "hr.appraisal"

    def action_invite(self):
        self.check_singleton()
        appraisal = self.appraisal_id

        ctx = {
            "url": self._get_appraisal_url(),
        }
        context_self = self.with_context(ctx)
        subject = context_self._render_field("subject", appraisal.ids)[appraisal.id]
        body = context_self._render_field("body", appraisal.ids)[appraisal.id]

        appraisal.message_post(
            author_id=self.author_id.id,
            body=body,
            email_layout_xmlid="mail.mail_notification_light",
            message_type="comment",
            partner_ids=self.recipient_ids.ids,
            subject=subject,
            attachment_ids=self.template_id.attachment_ids.ids,
        )

        return {
            "view_mode": "form",
            "res_model": "hr.appraisal",
            "type": "ir.actions.act_window",
            "target": "current",
            "res_id": appraisal.id,
        }

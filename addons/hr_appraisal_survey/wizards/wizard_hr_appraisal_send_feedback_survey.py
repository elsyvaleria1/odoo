import logging

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class WizardHrAppraisalSendFeedbackSurvey(models.TransientModel):
    _name = "wizard.hr.appraisal.send.feedback.survey"
    _inherit = ["mixin.mail.composer", "mixin.hr"]
    _description = "Ask Feedback for Appraisal"

    def _default_appraisal_id(self):
        active_id = self.env.context.get("active_id", None)
        if active_id:
            return active_id

        active_domain = self.env.context.get("active_domain", [])
        for d in active_domain:
            if isinstance(d, (list, tuple)) and len(d) == 3 and d[0] == "appraisal_id":
                return d[2]
        return None

    appraisal_id = fields.Many2one(
        comodel_name="hr.appraisal",
        default=lambda self: self._default_appraisal_id(),
    )
    employee_id = fields.Many2one(
        related="appraisal_id.employee_id",
        string="Appraisal Employee",
    )
    template_id = fields.Many2one(
        default=lambda self: self.env.ref(
            "hr_appraisal_survey.mail_template_appraisal_ask_feedback",
            raise_if_not_found=False,
        )
    )
    author_id = fields.Many2one(
        comodel_name="res.partner",
        default=lambda self: self.env.user.partner_id.id,
        required=True,
    )
    allowed_survey_template_ids = fields.Many2many(
        comodel_name="survey.survey",
        compute="_compute_allowed_survey_template_ids",
    )
    survey_template_id = fields.Many2one(
        comodel_name="survey.survey",
        compute="_compute_survey_template_id",
        precompute=True,
        compute_sudo=False,
        store=True,
        readonly=False,
        required=True,
        domain="[('id', 'in', allowed_survey_template_ids)]",
    )
    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Recipients",
        required=True,
    )
    deadline = fields.Date(
        string="Answer Deadline",
        compute="_compute_deadline",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    user_body = fields.Html(string="User Contents")

    # Overrides of mixin.mail.composer
    @api.depends(
        "survey_template_id"
    )  # fake trigger otherwise not computed in new mode
    def _compute_render_model(self) -> None:
        self.render_model = "survey.user_input"

    @api.depends("employee_id")
    def _compute_subject(self) -> None:
        for wizard_su in self.filtered(
            lambda w: w.employee_id and w.template_id
        ).sudo():
            wizard_su.subject = wizard_su.with_context(
                employee_id=wizard_su.employee_id
            )._render_template(
                wizard_su.template_id.subject,
                "hr.appraisal",
                wizard_su.appraisal_id.ids,
                engine="inline_template",
                options={"post_process": True},
            )[wizard_su.appraisal_id.id]

    @api.depends("template_id", "employee_ids")
    def _compute_body(self) -> None:
        for wizard in self:
            langs = set(wizard.employee_ids.partner_id.mapped("lang")) - {False}
            if len(langs) == 1:
                wizard = wizard.with_context(lang=langs.pop())
            super(WizardHrAppraisalSendFeedbackSurvey, wizard)._compute_body()

    @api.depends("appraisal_id")
    def _compute_allowed_survey_template_ids(self) -> None:
        # survey.survey orders by create_date alone, and the templates shipped
        # with this module are created in the same transaction, to the same
        # microsecond: without a tiebreaker the default below is decided by
        # physical row order
        all_appraisal_templates = self.env["survey.survey"].search(
            [("survey_type", "=", "appraisal")], order="create_date DESC, id ASC"
        )
        for wizard in self:
            wizard.allowed_survey_template_ids = (
                wizard.appraisal_id.appraisal_template_id.survey_template_ids
                or all_appraisal_templates
            )

    @api.depends("allowed_survey_template_ids")
    def _compute_survey_template_id(self) -> None:
        for wizard in self:
            if not wizard.survey_template_id:
                # allowed_survey_template_ids is not stored, so on a new record
                # it yields NewId wrappers; a stored Many2one writes those as
                # NULL, which the NOT NULL of required=True then rejects
                wizard.survey_template_id = wizard.allowed_survey_template_ids[
                    :1
                ]._origin

    @api.depends("appraisal_id.date_close")
    def _compute_deadline(self) -> None:
        today = fields.Date.today()
        date_in_month = today + relativedelta(months=1)
        for wizard in self:
            date_close = wizard.appraisal_id.date_close
            if not date_close:
                # the wizard opens without an appraisal in context too
                wizard.deadline = date_in_month
                continue
            # allow "last day" feedback fill by adding 1 day, and never propose
            # a deadline action_send would refuse and the picker would forbid
            wizard.deadline = max(
                today + relativedelta(days=1),
                min(date_in_month, date_close + relativedelta(days=1)),
            )

    @api.onchange("employee_ids")
    def _onchange_employee_ids(self) -> dict | None:
        emailless_employees = self.employee_ids.filtered(
            lambda e: not (e.work_email or e.user_id.partner_id.email)
        )
        if emailless_employees:
            warning = {
                "title": self.env._("Missing email"),
                "message": self.env._(
                    "The following employees do not have any email: \n%s",
                    ", ".join(emailless_employees.mapped("name")),
                ),
                "type": "notification",
            }
            self.employee_ids -= emailless_employees
            return {"warning": warning}
        return None

    def _get_reachable_partner(self, employee):
        # `_create_answer` uses `partner.email` and ignores any `email` it is
        # also given whenever `partner` is truthy, so a partner is only safe
        # to pass here when its OWN email is the reachable one - never a
        # partner picked for another reason (e.g. partner_id existing)
        # while the actual address lives on a different partner.
        contact = employee.partner_id
        if contact and contact.email:
            _debug.logic("feedback_partner", by="employee_partner", employee=employee)
            return contact
        user_partner = employee.user_id.partner_id
        if user_partner and user_partner.email:
            _debug.logic("feedback_partner", by="user_partner", employee=employee)
            return user_partner
        _debug.logic("feedback_partner", by="none", employee=employee)
        return self.env["res.partner"]

    def _prepare_survey_answers(self, employees):
        answers = self.env["survey.user_input"]
        employees_info = employees.mapped(
            lambda employee: {
                "id": employee.id,
                "email": employee.work_email or employee.user_id.partner_id.email,
                "partner_id": self._get_reachable_partner(employee),
            }
        )
        emails = [e["email"] for e in employees_info]
        partner_ids = [e["partner_id"]["id"] for e in employees_info]

        existing_answers = self.env["survey.user_input"].search(
            [
                "&",
                "&",
                ("survey_id", "=", self.survey_template_id.id),
                ("appraisal_id", "=", self.appraisal_id.id),
                "|",
                "&",
                ("partner_id", "in", partner_ids),
                ("partner_id", "!=", False),
                "&",
                ("email", "in", emails),
                ("email", "!=", False),
            ]
        )
        employees_done = []
        _debug.pipeline(
            "feedback_answers",
            appraisal=self.appraisal_id,
            employees=employees,
            existing=existing_answers,
        )
        if existing_answers:
            existing_answer_emails = existing_answers.filtered("email").mapped("email")
            existing_answer_partners_id = existing_answers.filtered(
                "partner_id"
            ).mapped("partner_id")
            employees_done.extend(
                employee_data
                for employee_data in employees_info
                if employee_data.get("email") in existing_answer_emails
                or employee_data.get("partner_id") in existing_answer_partners_id
            )
            existing_answers = existing_answers.sorted(
                lambda answer: answer.create_date, reverse=True
            )
            for employee_done in employees_done:
                answers |= next(
                    (
                        a
                        for a in existing_answers
                        if (
                            a.partner_id
                            and a.partner_id == employee_done.get("partner_id")
                        )
                        or (a.email and a.email == employee_done.get("email"))
                    ),
                    existing_answers.browse(),
                )

        done_ids = {employee_data["id"] for employee_data in employees_done}
        for new_employee in (e for e in employees_info if e["id"] not in done_ids):
            answers |= self.survey_template_id.sudo()._create_answer(
                partner=new_employee["partner_id"],
                email=new_employee["email"],
                check_attempts=False,
                deadline=self.deadline,
            )
        return answers

    def _send_mail(self, answer):
        """Create mail specific for recipient containing notably its access token"""
        ctx = {
            "logged_user": self.env.user.name,
            "employee": self.employee_id.name,
            "deadline": self.deadline,
            "user_body": self.user_body,
        }
        body = self.with_context(**ctx)._render_field("body", answer.ids)[answer.id]
        mail_values = {
            "email_from": self.author_id.email_formatted,
            "author_id": self.author_id.id,
            "model": None,
            "res_id": None,
            "subject": self.subject,
            "body_html": body,
            "auto_delete": True,
        }
        if answer.partner_id:
            mail_values["recipient_ids"] = [Command.link(answer.partner_id.id)]
        else:
            mail_values["email_to"] = answer.email

        mail_values["body_html"] = self.env["mixin.mail.render"]._render_encapsulate(
            "mail.mail_notification_light",
            mail_values["body_html"],
            context_record=self.survey_template_id,
        )
        return self.env["mail.mail"].sudo().create(mail_values)

    def action_send(self):
        self.check_singleton()

        if fields.Date.today() > self.deadline:
            raise UserError(self.env._("Please set an Answer Deadline in the future"))

        # the onchange only strips emailless employees on a value entered
        # through the form; a caller that creates/writes employee_ids
        # directly (bypassing the onchange) must be caught here too, or an
        # unreachable answer + mail gets created for them silently
        employees = self.employee_ids.filtered(
            lambda e: e.work_email or e.user_id.partner_id.email
        )
        if not employees:
            raise UserError(
                self.env._("None of the selected employees have an email address.")
            )

        answers = self._prepare_survey_answers(employees)
        answers.sudo().write(
            {"appraisal_id": self.appraisal_id.id, "deadline": self.deadline}
        )
        for answer in answers:
            self._send_mail(answer)

        for employee in employees.filtered(
            lambda e: (
                e.user_id
                and e.user_id.has_group("hr_appraisal.group_hr_appraisal_user")
            )
        ):
            answer = answers.filtered_domain(
                [
                    (
                        "partner_id",
                        "in",
                        (employee.user_id.partner_id | employee.partner_id).ids,
                    )
                ]
            )
            if answer:
                self.appraisal_id.with_context(
                    mail_activity_quick_update=True
                ).activity_schedule(
                    "mail.mail_activity_data_todo",
                    self.deadline,
                    summary=self.env._("Fill the feedback form on survey"),
                    note=self.env._(
                        'An appraisal feedback was requested. Please take time to fill the <a href="%s" target="_blank">survey</a>',
                        answer.get_start_url(),
                    ),
                    user_id=employee.user_id.id,
                )

        self.appraisal_id.employee_feedback_ids |= employees
        self.appraisal_id.survey_ids |= self.survey_template_id
        return {"type": "ir.actions.act_window_close"}

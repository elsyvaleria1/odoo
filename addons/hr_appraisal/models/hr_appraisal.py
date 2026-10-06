import datetime
import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import convert, frozendict
from odoo.tools.misc import format_date

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class HrAppraisal(models.Model):
    _name = "hr.appraisal"
    _inherit = ["mixin.hr", "mixin.mail.thread", "mixin.mail.activity"]
    _description = "Employee Appraisal"
    _order = "state, date_close, id desc"
    _rec_name = "employee_id"
    _mail_post_access = "read"
    _access_anchors = frozendict(
        {
            "employee": "employee_id",
            "owner": "manager_ids.user_id",
        }
    )

    def _get_default_employee(self):
        if (
            self.env.context.get("active_model") == "hr.employee"
            and "active_id" in self.env.context
        ):
            return self.env.context.get("active_id")
        elif (
            self.env.context.get("active_model") == "res.users"
            and "active_id" in self.env.context
        ):
            return (
                self.env["res.users"].browse(self.env.context["active_id"]).employee_id
            )
        if not self.env.user.has_group("hr_appraisal.group_hr_appraisal_user"):
            return self.env.user.employee_id
        return None

    active = fields.Boolean(default=True)
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        default=lambda self: self._get_default_employee(),
        index=True,
        required=True,
        ondelete="cascade",
    )
    employee_user_id = fields.Many2one(
        comodel_name="res.users",
        related="employee_id.user_id",
        string="Employee User",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="employee_id.company_id",
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        compute="_compute_department_id",
        store=True,
    )
    job_id = fields.Many2one(
        comodel_name="hr.job",
        compute="_compute_job_id",
        store=True,
    )
    image_128 = fields.Image(related="employee_id.image_128")
    image_1920 = fields.Image(related="employee_id.image_1920")
    avatar_128 = fields.Image(related="employee_id.avatar_128")
    avatar_1920 = fields.Image(related="employee_id.avatar_1920")
    last_appraisal_id = fields.Many2one(
        comodel_name="hr.appraisal",
        related="employee_id.last_appraisal_id",
    )
    employee_appraisal_count = fields.Integer(related="employee_id.appraisal_count")
    uncomplete_goals_count = fields.Integer(
        related="employee_id.uncomplete_goals_count"
    )
    appraisal_template_id = fields.Many2one(
        comodel_name="hr.appraisal.template",
        compute="_compute_appraisal_template",
        store=True,
        readonly=False,
        domain="[('department_ids', 'in', [department_id, False])]",
        check_company=True,
    )
    employee_feedback_template = fields.Html(
        translate=True,
        compute="_compute_feedback_templates",
    )
    manager_feedback_template = fields.Html(
        translate=True,
        compute="_compute_feedback_templates",
    )

    date_close = fields.Date(
        string="Appraisal Date",
        default=lambda self: datetime.date.today() + relativedelta(months=+1),
        index=True,
        required=True,
        help="Closing date of the current appraisal",
    )
    next_appraisal_date = fields.Date(
        related="employee_id.next_appraisal_date",
        readonly=False,
        help="Date where the new appraisal will be automatically created",
    )
    state = fields.Selection(
        selection=[("1_new", "Draft"), ("2_pending", "Ongoing"), ("3_done", "Done")],
        string="Status",
        default="1_new",
        index=True,
        copy=False,
        required=True,
        group_expand=True,
        tracking=True,
    )
    manager_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="appraisal_manager_rel",
        column1="hr_appraisal_id",
        default=lambda self: self.env.user.employee_id,
        domain="[('id', '!=', employee_id), ('active', '=', 'True'), '|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        context={"active_test": False},
    )
    is_manager = fields.Boolean(compute="_compute_user_manager_rights")
    employee_autocomplete_ids = fields.Many2many(
        comodel_name="hr.employee",
        compute="_compute_employee_autocomplete",
        compute_sudo=True,
    )
    waiting_feedback = fields.Boolean(
        string="Waiting Feedback from Employee/Managers",
        compute="_compute_waiting_feedback",
    )
    employee_feedback = fields.Html(
        compute="_compute_employee_feedback",
        store=True,
        readonly=False,
        groups="hr_appraisal.group_hr_appraisal_user",
    )
    accessible_employee_feedback = fields.Html(
        compute="_compute_accessible_employee_feedback",
        inverse="_inverse_accessible_employee_feedback",
    )
    show_employee_feedback_full = fields.Boolean(
        compute="_compute_show_employee_feedback_full"
    )
    manager_feedback = fields.Html(
        compute="_compute_manager_feedback",
        store=True,
        readonly=False,
        groups="hr_appraisal.group_hr_appraisal_user",
    )
    accessible_manager_feedback = fields.Html(
        compute="_compute_accessible_manager_feedback",
        inverse="_inverse_accessible_manager_feedback",
    )
    show_manager_feedback_full = fields.Boolean(
        compute="_compute_show_manager_feedback_full"
    )
    employee_feedback_published = fields.Boolean(
        default=True,
        tracking=True,
        help="If greened, the manager will be able to see and edit your feedback. Otherwise, your feedback is blurred and visible only to you.",
    )
    manager_feedback_published = fields.Boolean(
        default=True,
        tracking=True,
        help="If greened, the employee will be able to see your feedback. Otherwise, your feedback is blurred and visible only to you.",
    )
    can_see_employee_publish = fields.Boolean(compute="_compute_buttons_display")
    can_see_manager_publish = fields.Boolean(compute="_compute_buttons_display")
    assessment_note = fields.Many2one(
        comodel_name="hr.appraisal.note",
        string="Final Rating",
        check_company=True,
        groups="hr_appraisal.group_hr_appraisal_user",
        help="This field is not visible to the Employee.",
    )
    accessible_assessment_note = fields.Many2one(
        comodel_name="hr.appraisal.note",
        string="Accessible Final Rating",
        compute="_compute_accessible_assessment_note",
        inverse="_inverse_accessible_assessment_note",
        check_company=True,
    )
    note = fields.Html(
        string="Private Note",
        groups="hr_appraisal.group_hr_appraisal_user",
    )
    accessible_note = fields.Html(
        string="Accessible Private Note",
        compute="_compute_accessible_note",
        inverse="_inverse_accessible_note",
    )
    appraisal_plan_posted = fields.Boolean()
    appraisal_properties = fields.Properties(
        definition="department_id.appraisal_properties_definition",
        string="Properties",
        precompute=False,
    )
    duplicate_appraisal_id = fields.Many2one(
        comodel_name="hr.appraisal",
        export_string_translation=False,
        compute="_compute_duplicate_appraisal_id",
        store=False,
    )

    @api.depends("employee_id", "manager_ids")
    def _compute_duplicate_appraisal_id(self) -> None:
        """
        Note: We only care for duplicate_appraisal_id when we create a
        new appraisal. This field is currently only used in form view
        and for performance reasons it should rather stay that way.
        """
        ongoing_appraisals = self.search(
            [
                ("state", "in", ["1_new", "2_pending"]),
                ("employee_id", "in", self.employee_id.ids),
                ("manager_ids", "in", self.manager_ids.ids),
            ],
            order="date_close",
        )
        self.duplicate_appraisal_id = False
        for appraisal in self:
            if appraisal.id or appraisal.state != "1_new":
                continue
            for ongoing_appraisal in ongoing_appraisals:
                if (
                    ongoing_appraisal.manager_ids == appraisal.manager_ids._origin
                    and ongoing_appraisal.employee_id == appraisal.employee_id
                    and ongoing_appraisal.id != appraisal.id
                ):
                    appraisal.duplicate_appraisal_id = ongoing_appraisal.id
                    break

    @api.depends("employee_id.department_id")
    def _compute_department_id(self) -> None:
        for appraisal in self:
            appraisal.department_id = appraisal.employee_id.department_id

    @api.depends("employee_id.job_id")
    def _compute_job_id(self) -> None:
        for appraisal in self:
            appraisal.job_id = appraisal.employee_id.job_id

    @api.depends_context("uid")
    # `state` is read by both passes below, and the flags it produces gate more
    # than buttons: `can_see_employee_publish` decides whether
    # `_compute_accessible_employee_feedback` discloses the raw feedback and
    # whether `_inverse_accessible_employee_feedback` accepts a write. Without
    # it here, a `state` write earlier in the same transaction left the flag
    # stale and a manager could overwrite the appraisee's own feedback.
    @api.depends("employee_id", "manager_ids", "state")
    def _compute_buttons_display(self) -> None:
        # Kept only for the `self - new_appraisals` pass below; the loop that
        # follows assigns both flags for every record, so pre-setting them here
        # had no observable effect.
        new_appraisals = self.filtered(lambda a: a.state == "1_new")
        user_employees = self.env.user.employee_ids
        is_manager = self.env.user.has_group("hr_appraisal.group_hr_appraisal_user")
        for appraisal in self:
            user_employee_in_appraisal_manager = bool(
                set(user_employees.ids) & set(appraisal.manager_ids.ids)
            )
            # Appraisal manager can edit feedback in draft state
            appraisal.can_see_employee_publish = (
                appraisal.employee_id in user_employees
                or (user_employee_in_appraisal_manager and appraisal.state == "1_new")
            )
            appraisal.can_see_manager_publish = user_employee_in_appraisal_manager
        for appraisal in self - new_appraisals:
            if (
                is_manager
                and not appraisal.can_see_employee_publish
                and not appraisal.can_see_manager_publish
            ):
                (
                    appraisal.can_see_employee_publish,
                    appraisal.can_see_manager_publish,
                ) = True, True

    @api.depends_context("uid")
    def _compute_employee_autocomplete(self) -> None:
        self.employee_autocomplete_ids = self.env.user.get_employee_autocomplete_ids()

    @api.depends_context("uid")
    @api.depends("manager_ids", "employee_id", "employee_id.parent_id")
    def _compute_user_manager_rights(self) -> None:
        # `recordset in recordset` is `len(item) == 1 and item.id in self._ids`,
        # so it is False for any user holding more than one `hr.employee` —
        # which `_user_uniq`, unique on (user_id, company_id), allows. Such a
        # manager lost every button on their own direct report's appraisal.
        # `_compute_buttons_display` above already uses the set intersection.
        user_employee_ids = set(self.env.user.employee_ids.ids)
        is_appraisal_user = self.env.user.has_group(
            "hr_appraisal.group_hr_appraisal_user"
        )
        for appraisal in self:
            appraisal.is_manager = is_appraisal_user or bool(
                user_employee_ids
                & set((appraisal.manager_ids | appraisal.employee_id.parent_id).ids)
            )

    @api.depends_context("uid")
    # `employee_id.user_id`, not `employee_id`: the compute reads the user
    # behind the employee, so linking an employee record to a user must
    # invalidate the flag.
    @api.depends("employee_id.user_id", "employee_feedback_published")
    def _compute_show_employee_feedback_full(self) -> None:
        for appraisal in self:
            is_appraisee = appraisal.employee_id.user_id == self.env.user
            appraisal.show_employee_feedback_full = (
                is_appraisee and not appraisal.employee_feedback_published
            )

    @api.depends_context("uid")
    # `manager_ids.user_id` for the same reason as above.
    @api.depends("manager_ids.user_id", "manager_feedback_published")
    def _compute_show_manager_feedback_full(self) -> None:
        for appraisal in self:
            is_appraiser = self.env.user in appraisal.manager_ids.user_id
            appraisal.show_manager_feedback_full = (
                is_appraiser and not appraisal.manager_feedback_published
            )

    @api.depends("department_id", "appraisal_template_id")
    def _compute_employee_feedback(self) -> None:
        for appraisal in self.filtered(lambda a: a.state in ["1_new", "2_pending"]):
            employee_template = appraisal._get_appraisal_template("employee")
            if appraisal.state == "1_new":
                appraisal.employee_feedback = employee_template
            else:
                appraisal.employee_feedback = (
                    appraisal.employee_feedback or employee_template
                )

    @api.depends("department_id", "appraisal_template_id")
    def _compute_manager_feedback(self) -> None:
        for appraisal in self.filtered(lambda a: a.state in ["1_new", "2_pending"]):
            manager_template = appraisal._get_appraisal_template("manager")
            if appraisal.state == "1_new":
                appraisal.manager_feedback = manager_template
            else:
                appraisal.manager_feedback = (
                    appraisal.manager_feedback or manager_template
                )

    @api.depends("department_id", "company_id", "appraisal_template_id")
    def _compute_feedback_templates(self) -> None:
        for appraisal in self:
            appraisal.employee_feedback_template = appraisal._get_appraisal_template(
                "employee"
            )
            appraisal.manager_feedback_template = appraisal._get_appraisal_template(
                "manager"
            )

    @api.depends("department_id", "company_id")
    def _compute_appraisal_template(self) -> None:
        all_department_template_ids = self.env["hr.appraisal.template"].search(
            [
                ("department_ids", "=", False),
                ("company_id", "in", self.company_id.ids + [False]),
            ]
        )
        for appraisal in self:
            appraisal.appraisal_template_id = (
                appraisal.appraisal_template_id
                or appraisal.department_id.appraisal_template_ids[:1]
                or all_department_template_ids.filtered_domain(
                    [("company_id", "in", [appraisal.company_id.id, False])]
                )[:1]
            )

    @api.depends("employee_feedback_published", "manager_feedback_published")
    def _compute_waiting_feedback(self) -> None:
        for appraisal in self:
            appraisal.waiting_feedback = (
                not appraisal.employee_feedback_published
                or not appraisal.manager_feedback_published
            )

    @api.depends("employee_id", "date_close")
    @api.depends_context("include_date_in_name")
    def _compute_display_name(self):
        if not self.env.context.get("include_date_in_name"):
            return super()._compute_display_name()
        for appraisal in self:
            appraisal.display_name = self.env._(
                "Appraisal for %(employee)s on %(date)s",
                employee=appraisal.employee_id.name,
                date=appraisal.date_close,
            )
        return None

    @api.onchange("employee_id")
    def _onchange_employee_id(self) -> None:
        self = self.sudo()  # fields are not on the employee public
        if self.employee_id:
            manager = self.employee_id.parent_id or self.env.user.employee_id
            self.manager_ids = manager if manager != self.employee_id else False
            # Allow indirect managers to request appraisals for employees
            if (
                self.env.user.employee_id != self.employee_id
                and not self.env.user.has_group("hr_appraisal.group_hr_appraisal_user")
            ):
                self.manager_ids |= self.env.user.employee_id
            self.department_id = self.employee_id.department_id

    def subscribe_employees(self) -> None:
        for appraisal in self:
            partners_ids = (
                appraisal.manager_ids.sudo().related_partner_id
                + appraisal.employee_id.sudo().related_partner_id
            ).ids
            appraisal.message_subscribe(partner_ids=partners_ids)

    def send_appraisal(self) -> None:
        # FIXME: probably some cleanup to do here
        if not self:
            _debug.logic("appraisal_mail_skipped", reason="empty_recordset")
            # Called on an empty recordset from create()/write() whenever
            # nothing needs sending; without this the warning below fires with
            # no appraisals to name.
            return
        if not self.env.user.email:
            _debug.logic(
                "appraisal_mail_skipped",
                reason="acting_user_has_no_email",
                appraisals=self,
                user=self.env.user,
            )
            # A configuration fault, not a per-recipient skip: without it every
            # notification below is silently dropped and the appraisal moves to
            # Ongoing with nobody informed.
            _logger.warning(
                "No appraisal notification sent for %s: the acting user %s has no email address.",
                self.ids,
                self.env.user.display_name,
            )
            return
        for appraisal in self:
            confirmation_mail_template = (
                appraisal.company_id.appraisal_confirm_mail_template
            )
            mapped_data = {
                appraisal.employee_id: confirmation_mail_template,
                **dict.fromkeys(appraisal.manager_ids, confirmation_mail_template),
            }
            for employee, mail_template in mapped_data.items():
                if not employee.work_email or not mail_template:
                    continue
                ctx = {
                    "employee_to_name": appraisal.employee_id.name,
                    "recipient_users": employee.user_id,
                    "url": "/mail/view?model=%s&res_id=%s"
                    % ("hr.appraisal", appraisal.id),
                }
                mail_template = mail_template.with_context(**ctx)
                subject = mail_template._render_field("subject", appraisal.ids)[
                    appraisal.id
                ]
                body = mail_template._render_field("body_html", appraisal.ids)[
                    appraisal.id
                ]
                # post the message
                mail_values = {
                    "email_from": self.env.user.email_formatted,
                    "author_id": self.env.user.partner_id.id,
                    "model": None,
                    "res_id": None,
                    "subject": subject,
                    "body_html": body,
                    "auto_delete": True,
                    "email_to": employee.work_email,
                }
                mail_values["body_html"] = self.env[
                    "mixin.mail.render"
                ]._render_encapsulate(
                    "mail.mail_notification_light",
                    mail_values["body_html"],
                    context_record=appraisal,
                    add_context={
                        "record_name": self.env._("Appraisal Request"),
                    },
                )
                self.env["mail.mail"].sudo().create(mail_values)

                from_cron = self.env.context.get("from_cron")
                # When cron creates appraisal, it creates specific activities
                # In this case, no need to create activities, not to be repetitive
                if employee.user_id and not from_cron:
                    appraisal.activity_schedule(
                        "mail.mail_activity_data_todo",
                        appraisal.date_close,
                        summary=self.env._("Appraisal Form to Fill"),
                        note=self.env._(
                            "Fill appraisal for %s",
                            appraisal.employee_id._get_html_link(),
                        ),
                        user_id=employee.user_id.id,
                    )

    def _remove_employee_date_without_employee_write(self, vals_list) -> None:
        # next_appraisal_date writes through to the employee; an employee
        # requesting their own appraisal cannot write their employee record,
        # and the form sends the date back untouched.
        if self.env["hr.employee"].has_access("write"):
            return
        for vals in vals_list:
            vals.pop("next_appraisal_date", None)

    @api.model_create_multi
    def create(self, vals_list):
        self._remove_employee_date_without_employee_write(vals_list)
        appraisals = super().create(vals_list)
        appraisals_to_send = self.env["hr.appraisal"]
        # Read the state off the created record, not out of the vals: `state`
        # defaults to '1_new', so the common case - creating a draft without
        # naming the state - never reached the branch below.
        for appraisal in appraisals:
            if appraisal.state == "2_pending":
                appraisals_to_send |= appraisal
            elif appraisal.state == "1_new":
                appraisal.employee_id.sudo().write(
                    {
                        "last_appraisal_id": appraisal.id,
                    }
                )
        _debug.lifecycle(
            "create",
            appraisals=appraisals,
            count=len(vals_list),
            to_send=appraisals_to_send,
        )
        appraisals_to_send.send_appraisal()
        # FIXME: check if we can use suggested recipients instead
        appraisals.subscribe_employees()
        return appraisals

    @api.depends(
        "employee_feedback", "can_see_employee_publish", "employee_feedback_published"
    )
    def _compute_accessible_employee_feedback(self) -> None:
        for appraisal in self:
            if (
                appraisal.can_see_employee_publish
                or appraisal.employee_feedback_published
            ):
                appraisal.accessible_employee_feedback = (
                    appraisal.sudo().employee_feedback
                )
            else:
                appraisal.accessible_employee_feedback = self.env._("Unpublished")

    def _inverse_accessible_employee_feedback(self) -> None:
        for appraisal in self:
            if appraisal.can_see_employee_publish:
                appraisal.sudo().employee_feedback = (
                    appraisal.accessible_employee_feedback
                )
            else:
                raise UserError(
                    self.env._("The employee feedback cannot be changed by managers.")
                )

    @api.depends(
        "manager_feedback", "can_see_manager_publish", "manager_feedback_published"
    )
    def _compute_accessible_manager_feedback(self) -> None:
        for appraisal in self:
            if (
                appraisal.can_see_manager_publish
                or appraisal.manager_feedback_published
            ):
                appraisal.accessible_manager_feedback = (
                    appraisal.sudo().manager_feedback
                )
            else:
                appraisal.accessible_manager_feedback = self.env._("Unpublished")

    def _inverse_accessible_manager_feedback(self) -> None:
        for appraisal in self:
            if appraisal.can_see_manager_publish:
                appraisal.sudo().manager_feedback = (
                    appraisal.accessible_manager_feedback
                )
            else:
                raise UserError(
                    self.env._("The manager feedback cannot be changed by an employee.")
                )

    def _is_appraisee(self) -> bool:
        self.check_singleton()
        return self.employee_id.user_id == self.env.user

    @api.depends_context("uid")
    @api.depends("note", "employee_id")
    def _compute_accessible_note(self) -> None:
        for appraisal in self:
            if appraisal._is_appraisee():
                appraisal.accessible_note = self.env._("Note")
            else:
                appraisal.accessible_note = appraisal.sudo().note

    def _inverse_accessible_note(self) -> None:
        # The appraisee only ever sees the placeholder, so writing it back is a
        # no-op we must tolerate: the form sends every field it holds on save.
        for appraisal in self.filtered(lambda a: not a._is_appraisee()):
            appraisal.sudo().note = appraisal.accessible_note

    @api.depends_context("uid")
    @api.depends("assessment_note", "employee_id")
    def _compute_accessible_assessment_note(self) -> None:
        for appraisal in self:
            if appraisal._is_appraisee():
                appraisal.accessible_assessment_note = False
            else:
                appraisal.accessible_assessment_note = appraisal.sudo().assessment_note

    def _inverse_accessible_assessment_note(self) -> None:
        for appraisal in self.filtered(lambda a: not a._is_appraisee()):
            appraisal.sudo().assessment_note = appraisal.accessible_assessment_note

    def _get_appraisal_template(self, template):
        self.check_singleton()
        if not self.appraisal_template_id:
            return False
        if template == "employee":
            return self.appraisal_template_id.appraisal_employee_feedback_template
        else:
            return self.appraisal_template_id.appraisal_manager_feedback_template

    def _find_previous_appraisals(self):
        # Group once instead of scanning the whole result per record, and order
        # by id: two appraisals created in the same transaction share a
        # create_date to the microsecond, so a strict `<` on it made neither the
        # other's predecessor.
        by_employee = (
            self.env["hr.appraisal"]
            .search(
                [("employee_id", "in", self.employee_id.ids)],
                order="id desc",
            )
            .grouped("employee_id")
        )
        result = {}
        for appraisal in self:
            for candidate in by_employee.get(appraisal.employee_id, self.browse()):
                if candidate.id < appraisal.id:
                    result[appraisal.id] = candidate
                    break
        return result

    def write(self, vals):
        _debug.lifecycle("write", appraisals=self, fields=list(vals))
        self._remove_employee_date_without_employee_write([vals])
        if "manager_feedback_published" in vals and not all(
            a.can_see_manager_publish for a in self
        ):
            _debug.logic("publish_refused", reason="not_manager", appraisals=self)
            raise UserError(
                self.env._(
                    'The "Manager Feedback Published" cannot be changed by an employee.'
                )
            )

        force_published = self.env["hr.appraisal"]
        if vals.get("employee_feedback_published"):
            user_employees = self.env.user.employee_ids
            force_published = self.filtered(
                lambda a: (
                    (a.is_manager)
                    and not (
                        a.employee_feedback_published or a.employee_id in user_employees
                    )
                )
            )
        transitioning = vals.get("state") in ["2_pending", "3_done"]
        not_done_appraisal = self.env["hr.appraisal"]
        if transitioning:
            self.activity_ids.action_feedback()
            not_done_appraisal = self.filtered(lambda a: a.state != "3_done")
            published = vals.get("state") == "3_done"
            vals["employee_feedback_published"] = published
            vals["manager_feedback_published"] = published
        result = super().write(vals)
        if transitioning:
            # After the write, never before: the mails and the chatter messages
            # below render the appraisal, and _appraisal_plan_post reads the
            # employee's ongoing count. Running them first shipped pre-
            # transition data, and left them behind in the transaction when the
            # write itself failed.
            for appraisal in self:
                appraisal.employee_id.sudo().write(
                    {
                        "last_appraisal_id": appraisal.id,
                    }
                )
            if vals.get("state") == "2_pending":
                not_done_appraisal.send_appraisal()
            else:
                self._appraisal_plan_post()
                if self.env.user.partner_id.email_formatted:
                    body = self.env._(
                        "The appraisal's status has been set to Done by %s",
                        self.env.user.name,
                    )
                    # message_notify is single-record: notify each appraisal's
                    # own followers instead of leaking the last loop variable.
                    for appraisal in self:
                        appraisal.message_notify(
                            body=body,
                            subject=self.env._("Your Appraisal has been completed"),
                            partner_ids=appraisal.message_partner_ids.ids,
                        )
                        appraisal.message_post(body=body)
        if force_published:
            for appraisal in force_published:
                role = (
                    self.env._("Manager")
                    if self.env.user.employee_id in appraisal.manager_ids
                    else self.env._("Appraisal Officer")
                )
                appraisal.message_post(
                    body=self.env._(
                        "%(user)s decided, as %(role)s, to publish the employee's feedback",
                        user=self.env.user.name,
                        role=role,
                    )
                )
        return result

    def unlink(self):
        previous_appraisals = self._find_previous_appraisals()
        for appraisal in self:
            if (
                appraisal.employee_id
                and appraisal.employee_id.last_appraisal_id == appraisal
            ):
                previous_appraisal = previous_appraisals.get(appraisal.id)
                appraisal.employee_id.sudo().write(
                    {
                        "last_appraisal_id": previous_appraisal.id
                        if previous_appraisal
                        else False,
                    }
                )
        return super().unlink()

    def _appraisal_plan_post(self) -> None:
        odoobot = self.env.ref("base.partner_root")
        dates = self.employee_id.sudo()._upcoming_appraisal_creation_date()
        for appraisal in self:
            # The only ongoing appraisal is the current one
            if (
                not appraisal.appraisal_plan_posted
                and appraisal.company_id.appraisal_plan
                and appraisal.employee_id.sudo().ongoing_appraisal_count == 1
            ):
                date = dates[appraisal.employee_id.id]
                formated_date = format_date(self.env, date, date_format="MMM d y")
                body = self.env._(
                    "Thanks to your Appraisal Plan, without any new manual Appraisal, the new Appraisal will be automatically created on %s.",
                    formated_date,
                )
                appraisal._message_log(body=body, author_id=odoobot.id)
                appraisal.appraisal_plan_posted = True

    def _generate_activities(self) -> None:
        today = fields.Date.today()
        for appraisal in self:
            employee = appraisal.employee_id
            managers = appraisal.manager_ids
            last_appraisal_date = employee.last_appraisal_id.date_close
            last_appraisal_months = last_appraisal_date and (
                today.year - last_appraisal_date.year
            ) * 12 + (today.month - last_appraisal_date.month)
            if employee.user_id:
                # an appraisal has been just created
                if employee.appraisal_count == 1:
                    months = (
                        appraisal.date_close.year - employee.create_date.year
                    ) * 12 + (appraisal.date_close.month - employee.create_date.month)
                    note = self.env._(
                        "You arrived %s months ago. Your appraisal is created and you can fill it here.",
                        months,
                    )
                else:
                    note = self.env._(
                        "Your last appraisal was %s months ago. Your appraisal is created and you can fill it here.",
                        last_appraisal_months,
                    )
                appraisal.with_context(
                    mail_activity_quick_update=True
                ).activity_schedule(
                    "mail.mail_activity_data_todo",
                    today,
                    summary=self.env._("Appraisal to fill"),
                    note=note,
                    user_id=employee.user_id.id,
                )
                for manager in managers.filtered("user_id"):
                    if employee.appraisal_count == 1:
                        note = self.env._(
                            "The employee %(employee)s arrived %(months)s months ago. The appraisal is created and you can fill it here.",
                            employee=employee._get_html_link(),
                            months=months,
                        )
                    else:
                        note = self.env._(
                            "The last appraisal of %(employee)s was %(months)s months ago. The appraisal is created and you can fill it here.",
                            employee=appraisal.employee_id._get_html_link(),
                            months=last_appraisal_months,
                        )
                    appraisal.with_context(
                        mail_activity_quick_update=True
                    ).activity_schedule(
                        "mail.mail_activity_data_todo",
                        today,
                        summary=self.env._("Appraisal for %s to fill", employee.name),
                        note=note,
                        user_id=manager.user_id.id,
                    )

    @api.ondelete(at_uninstall=False)
    def _unlink_if_new_or_cancel(self) -> None:
        if any(appraisal.state != "1_new" for appraisal in self):
            raise UserError(self.env._("Oops! You can only delete draft appraisals."))

    def action_calendar_event(self):
        self.check_singleton()
        partners = (
            self.manager_ids.mapped("related_partner_id")
            | self.employee_id.related_partner_id
            | self.env.user.partner_id
        )
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "calendar.action_calendar_event"
        )
        action["context"] = {
            "default_partner_ids": partners.ids,
            "default_res_model": "hr.appraisal",
            "default_res_id": self.id,
            "default_name": self.env._("Appraisal of %s", self.employee_id.name),
            "initial_date": self.date_close,
        }
        action["domain"] = [("partner_ids", "in", partners.ids)]
        return action

    def action_confirm(self):
        _debug.lifecycle("confirm", appraisals=self)
        self.state = "2_pending"

    def action_done(self):
        appraisals_with_rating = self.browse(
            self.sudo().filtered("assessment_note").ids
        )
        # Validate the whole batch before writing anything: transitioning the
        # rated ones and then reporting failure left the batch half committed.
        if self - appraisals_with_rating:
            _debug.logic(
                "done_refused",
                reason="missing_rating",
                appraisals=self,
                unrated=self - appraisals_with_rating,
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Required:"),
                    "message": self.env._(
                        "Please set a final rating to validate these appraisals:\n- %s",
                        "\n- ".join(
                            (self - appraisals_with_rating).mapped("display_name")
                        ),
                    ),
                    "type": "danger",
                    "sticky": True,
                },
            }
        _debug.lifecycle("done", appraisals=appraisals_with_rating)
        appraisals_with_rating.state = "3_done"
        return None

    def action_back(self):
        _debug.lifecycle("back_to_new", appraisals=self)
        self.state = "1_new"
        self.sudo().assessment_note = False

    def action_reopen(self) -> None:
        _debug.lifecycle("reopen", appraisals=self)
        self.state = "2_pending"

    def action_view_employee_appraisals(self):
        view_id = self.env.ref(
            "hr_appraisal.hr_appraisal_view_tree_orderby_create_date"
        ).id
        return {
            "name": self.env._("Previous Appraisals"),
            "res_model": "hr.appraisal",
            "view_mode": "list,kanban,form,gantt,calendar,activity",
            "views": [
                (view_id, "list"),
                (False, "kanban"),
                (False, "form"),
                (False, "gantt"),
                (False, "calendar"),
                (False, "activity"),
            ],
            "domain": [("employee_id", "in", self.employee_id.ids)],
            "type": "ir.actions.act_window",
            "target": "current",
            "context": {
                "search_default_groupby_date_close": True,
            },
        }

    def action_view_goals(self):
        self.check_singleton()
        return {
            "name": self.env._("%s's Goals", self.employee_id.name),
            "view_mode": "kanban,list,form,graph",
            "res_model": "hr.appraisal.goal",
            "type": "ir.actions.act_window",
            "views": [
                (self.env.ref("hr_appraisal.hr_appraisal_goal_view_tree").id, "list"),
                (False, "kanban"),
                (self.env.ref("hr_appraisal.hr_appraisal_goal_view_form").id, "form"),
                (False, "graph"),
            ],
            "target": "current",
            "domain": [
                ("employee_ids", "=", self.employee_id.id),
                ("child_ids", "=", False),
            ],
            "context": {"default_employee_ids": self.employee_id.ids},
        }

    def action_send_appraisal_request(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.hr.appraisal.send",
            "target": "new",
            "name": self.env._("Appraisal Request"),
            "context": {"default_appraisal_id": self.id},
        }

    def action_view_appraisal_campaign_wizard(self) -> dict:
        employee_ids = False
        if self.env.context.get("active_model") == "hr.employee":
            employee_ids = self.env.context.get("active_ids")
        elif self.env.context.get("active_model") == "hr.appraisal":
            appraisals = self.env["hr.appraisal"].browse(
                self.env.context.get("active_ids")
            )
            employee_ids = appraisals.employee_id.ids
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Appraisal Campaign"),
            "res_model": "wizard.hr.appraisal.create",
            "view_mode": "form",
            "context": {
                "default_mode": "employee",
                "default_employee_ids": employee_ids,
            },
            "target": "new",
        }

    @api.model
    def has_demo_data(self) -> bool:
        if not self.env.user.has_group("hr_appraisal.group_hr_appraisal_user"):
            return True
        # This record only exists if the scenario has been already launched
        goal_tag = self.env.ref(
            "hr_appraisal.hr_appraisal_goal_tag_softskills", raise_if_not_found=False
        )
        if goal_tag:
            return True
        return bool(
            self.env["ir.module.module"].search_count(
                [
                    "&",
                    ("state", "in", ["installed", "to upgrade", "uninstallable"]),
                    ("demo", "=", True),
                ],
                limit=1,
            )
        )

    def _load_demo_data(self) -> dict | None:
        if self.has_demo_data():
            return None
        env_sudo = self.sudo().with_context({}).env
        env_sudo["hr.employee"]._load_scenario()
        convert.convert_file(
            env_sudo,
            "hr_appraisal",
            "data/scenarios/hr_appraisal_scenario.xml",
            None,
            mode="init",
        )
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

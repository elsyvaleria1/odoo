from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools.misc import clean_context

_debug = DebugLog(__name__)

HR_READABLE_FIELDS = [
    "active",
    "additional_note",
    "salary_bank_account_ids",
    "barcode",
    "birthday",
    "birthday_public_display",
    "child_ids",
    "children",
    "country_of_birth",
    "emergency_contact",
    "emergency_phone_ids",
    "employee_id",
    "employee_ids",
    "employee_resource_calendar_id",
    "is_hr_user",
    "is_system",
    "job_title",
    "km_home_work",
    "legal_name",
    "marital",
    "pin",
    "place_of_birth",
    "private_city",
    "private_country_id",
    "private_email",
    "private_phone_ids",
    "private_state_id",
    "private_street",
    "private_street2",
    "private_zip",
    "sex",
    "spouse_birthdate",
    "spouse_complete_name",
    "tag_ids",
    "visa_expire",
    "work_email",
    "work_location_id",
    "work_location_name",
    "work_location_type",
]


class ResUsers(models.Model):
    _inherit = "res.users"

    def action_request_information_change(self):
        return self.env["hr.employee.change.request"].action_open_my_request()

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + HR_READABLE_FIELDS

    def _domain_employee_ids(self):
        return [
            (
                "company_id",
                "in",
                self.env.company.ids + self.env.context.get("allowed_company_ids", []),
            )
        ]

    employee_ids = fields.One2many(
        comodel_name="hr.employee",
        inverse_name="user_id",
        string="Related employee",
        domain=_domain_employee_ids,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Company employee",
        compute="_compute_employee_id",
        search="_search_employee_id",
        store=False,
    )

    job_title = fields.Char(related="employee_id.job_title")
    work_email = fields.Char(
        related="employee_id.work_email",
        related_sudo=False,
        readonly=False,
    )
    tag_ids = fields.Many2many(
        related="employee_id.tag_ids",
        string="Employee Tags",
        related_sudo=False,
        readonly=False,
    )
    work_location_id = fields.Many2one(
        related="employee_id.work_location_id",
        related_sudo=False,
        readonly=False,
    )
    work_location_name = fields.Char(related="employee_id.work_location_name")
    work_location_type = fields.Selection(related="employee_id.work_location_type")
    marital = fields.Selection(
        related="employee_id.marital",
        related_sudo=False,
        readonly=False,
    )
    spouse_complete_name = fields.Char(
        related="employee_id.spouse_complete_name",
        related_sudo=False,
        readonly=False,
    )
    spouse_birthdate = fields.Date(
        related="employee_id.spouse_birthdate",
        related_sudo=False,
        readonly=False,
    )
    children = fields.Integer(
        related="employee_id.children",
        related_sudo=False,
        readonly=False,
    )
    legal_name = fields.Char(
        related="employee_id.legal_name",
        related_sudo=False,
        readonly=False,
    )
    birthday = fields.Date(
        related="employee_id.birthday",
        related_sudo=False,
        readonly=False,
    )
    birthday_public_display = fields.Boolean(
        related="employee_id.birthday_public_display",
        related_sudo=False,
        readonly=False,
    )
    place_of_birth = fields.Char(
        related="employee_id.place_of_birth",
        related_sudo=False,
        readonly=False,
    )
    country_of_birth = fields.Many2one(
        related="employee_id.country_of_birth",
        related_sudo=False,
        readonly=False,
    )
    sex = fields.Selection(
        related="employee_id.sex",
        related_sudo=False,
        readonly=False,
    )

    private_street = fields.Char(
        related="employee_id.private_street",
        string="Private Street",
        related_sudo=False,
        readonly=False,
    )
    private_street2 = fields.Char(
        related="employee_id.private_street2",
        string="Private Street2",
        related_sudo=False,
        readonly=False,
    )
    private_city = fields.Char(
        related="employee_id.private_city",
        string="Private City",
        related_sudo=False,
        readonly=False,
    )
    private_state_id = fields.Many2one(
        related="employee_id.private_state_id",
        string="Private State",
        related_sudo=False,
        readonly=False,
        domain="[('country_id', '=?', private_country_id)]",
    )
    private_zip = fields.Char(
        related="employee_id.private_zip",
        string="Private Zip",
        related_sudo=False,
        readonly=False,
    )
    private_country_id = fields.Many2one(
        related="employee_id.private_country_id",
        string="Private Country",
        related_sudo=False,
        readonly=False,
    )
    private_phone_ids = fields.Many2many(
        related="employee_id.private_phone_ids",
        readonly=False,
        groups="hr.group_hr_user",
    )
    private_email = fields.Char(
        related="employee_id.private_email",
        string="Private Email",
        related_sudo=False,
        readonly=False,
    )
    km_home_work = fields.Integer(
        related="employee_id.km_home_work",
        related_sudo=False,
        readonly=False,
    )
    emergency_contact = fields.Char(
        related="employee_id.emergency_contact",
        related_sudo=False,
        readonly=False,
    )
    emergency_phone_ids = fields.Many2many(
        related="employee_id.emergency_phone_ids",
        readonly=False,
        groups="hr.group_hr_user",
    )
    visa_expire = fields.Date(
        related="employee_id.visa_expire",
        related_sudo=False,
        readonly=False,
    )
    additional_note = fields.Text(
        related="employee_id.additional_note",
        related_sudo=False,
        readonly=False,
    )
    barcode = fields.Char(
        related="employee_id.barcode",
        related_sudo=False,
        readonly=False,
    )
    pin = fields.Char(
        related="employee_id.pin",
        related_sudo=False,
        readonly=False,
    )
    employee_count = fields.Integer(compute="_compute_employee_count")
    employee_resource_calendar_id = fields.Many2one(
        related="employee_id.resource_calendar_id",
        string="Employee's Working Hours",
        readonly=True,
    )
    salary_bank_account_ids = fields.Many2many(
        related="employee_id.salary_bank_account_ids"
    )

    create_employee = fields.Boolean(
        string="Technical field, whether to create an employee",
        default=False,
        store=False,
        copy=False,
    )
    create_employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Technical field, bind user to this employee on create",
        store=False,
        copy=False,
    )

    is_system = fields.Boolean(compute="_compute_is_system")
    is_hr_user = fields.Boolean(compute="_compute_is_hr_user")

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        employee_create_vals = []
        for user, vals in zip(res, vals_list, strict=True):
            if not vals.get("create_employee") and not vals.get("create_employee_id"):
                continue
            if vals.get("create_employee_id"):
                _debug.pipeline(
                    "employee_bound",
                    user=user.id,
                    employee=vals.get("create_employee_id"),
                )
                self.env["hr.employee"].browse(
                    vals.get("create_employee_id")
                ).user_id = user
            else:
                _debug.pipeline(
                    "employee_created", user=user.id, company=user.env.company.id
                )
                employee_create_vals.append(
                    dict(
                        name=user.name,
                        company_id=user.env.company.id,
                        **self.env["hr.employee"]._sync_user(user),
                    )
                )
        if employee_create_vals:
            employees = (
                self.env["hr.employee"]
                .with_context(clean_context(self.env.context))
                .create(employee_create_vals)
            )
            _debug.lifecycle("employees_created", employees=employees, users=res)
        return res

    @_debug.perf.timed
    def write(self, vals):
        hr_fields = [
            field_name
            for field_name, field in self._fields.items()
            if field.related_field
            and field.related_field.model_name == "hr.employee"
            and field_name in vals
        ]
        _debug.lifecycle("write", users=self, keys=sorted(vals), hr_fields=hr_fields)
        employee_domain = [
            *self.env["hr.employee"]._check_company_domain(self.env.company),
            ("user_id", "in", self.ids),
        ]

        self_sudo = self.sudo()
        old_hr_values = {
            field_name: {user.id: user[field_name] for user in self_sudo}
            for field_name in hr_fields
        }

        result = super().write(vals)

        changed_hr_fields = [
            field_name
            for field_name in hr_fields
            if any(
                old_hr_values[field_name][user.id] != user[field_name]
                for user in self_sudo
            )
        ]
        if changed_hr_fields:
            _debug.logic("hr_notified_of_change", users=self, changed=changed_hr_fields)
            self._notify_hr_of_personal_info_change(changed_hr_fields, employee_domain)
        return result

    @api.depends_context("uid")
    def _compute_is_system(self) -> None:
        self.is_system = self.env.user._is_system()

    @api.depends_context("uid")
    def _compute_is_hr_user(self) -> None:
        self.is_hr_user = self.env.user.has_group("hr.group_hr_user")

    @api.depends("employee_ids")
    def _compute_employee_count(self) -> None:
        for user in self.with_context(active_test=False):
            user.employee_count = len(user.employee_ids)

    @api.onchange("private_state_id")
    def _onchange_private_state_id(self) -> None:
        if self.private_state_id:
            self.private_country_id = self.private_state_id.country_id

    @api.model
    def get_views(self, views, options=None):
        preferences_view = self.env.ref("hr.res_users_view_form_preferences")
        preferences_form = preferences_view and [preferences_view.id, "form"]
        if preferences_form and preferences_form in views:
            views.remove(preferences_form)
            views.append(preferences_form)
        return super().get_views(views, options)

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        preferences_view = self.env.ref("hr.res_users_view_form_preferences")
        if preferences_view and view_id == preferences_view.id:
            _debug.logic("preferences_view_as_superuser", view=view_id)
            self = self.with_user(SUPERUSER_ID)
        return super().get_view(view_id, view_type, **options)

    def _get_notify_reason_and_partner_ids(self, employee) -> tuple:
        if employee.version_id.hr_responsible_id:
            return (
                self.env._(
                    "You are receiving this message because you are the HR Responsible of this employee."
                ),
                employee.version_id.hr_responsible_id.partner_id.ids,
            )
        return ("", [])

    @_debug.perf.timed
    def _notify_hr_of_personal_info_change(
        self, changed_field_names, employee_domain
    ) -> None:
        employees = self.env["hr.employee"].sudo().search(employee_domain)
        if not employees:
            _debug.logic(
                "personal_info_change_unnotified",
                users=self,
                reason="no_employee_in_company",
                company=self.env.company.id,
            )
            return
        get_field = self.env["ir.model.fields"]._get
        field_names = Markup().join(
            [
                Markup("<li>%s</li>") % get_field("res.users", fname).field_description
                for fname in changed_field_names
            ]
        )
        modified_by = self.env.user.name
        for employee in employees:
            reason_message, partner_ids = self._get_notify_reason_and_partner_ids(
                employee
            )
            if not partner_ids:
                _debug.logic(
                    "personal_info_change_unnotified",
                    employee=employee.id,
                    reason="no_hr_responsible",
                )
                continue
            _debug.pipeline(
                "personal_info_change_notified",
                employee=employee.id,
                changed=changed_field_names,
                partners=partner_ids,
            )
            employee.message_notify(
                body=Markup("<p>%s</p><p>%s</p><ul>%s</ul><p><em>%s</em></p>")
                % (
                    self.env._("Personal information update."),
                    self.env._("The following fields were modified by %s", modified_by),
                    field_names,
                    reason_message,
                ),
                partner_ids=partner_ids,
            )

    @api.model
    def action_get(self):
        if self.env.user.employee_id:
            action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
                "hr.res_users_action_my"
            )
            groups = {
                group_xml_id[0]: True
                for group_xml_id in self.env.user.all_group_ids._get_external_ids().values()
                if group_xml_id
            }
            action_context = (
                self.env["ir.actions.actions"]._eval_action_context(action["context"])
                if action["context"]
                else {}
            )
            action_context.update(groups)
            action["context"] = str(action_context)
            _debug.logic(
                "hr_profile_action",
                uid=self.env.uid,
                employee=self.env.user.employee_id.id,
            )
            return action
        return super().action_get()

    @_debug.perf.timed
    @api.depends("employee_ids")
    @api.depends_context("company")
    def _compute_employee_id(self) -> None:
        employee_per_user = {
            employee.user_id: employee
            for employee in self.env["hr.employee"].search(
                [
                    ("user_id", "in", self._origin.ids),
                    ("company_id", "=", self.env.company.id),
                ]
            )
        }
        for user in self:
            user.employee_id = employee_per_user.get(user._origin)

    def _search_employee_id(self, operator, value):
        IN_MAX = 10_000
        domain = Domain("employee_ids", operator, value)
        user_ids = (
            self.env["res.users"]
            .with_context(active_test=False)
            ._search(domain, limit=IN_MAX)
            .get_result_ids()
        )
        if len(user_ids) < IN_MAX:
            return Domain("id", "in", user_ids)

        _debug.logic("search_employee_id_fallback", matches_at_least=IN_MAX)
        return domain

    def action_create_employee(self) -> None:
        self.check_singleton()
        if self.env.company not in self.company_ids:
            raise AccessError(
                self.env._(
                    "You are not allowed to create an employee because the user does not have access rights for %s",
                    self.env.company.name,
                )
            )
        _debug.lifecycle(
            "action_create_employee", user=self.id, company=self.env.company.id
        )
        person = (
            self.env["hr.employee"]
            .with_context(active_test=False)
            .search(
                [
                    ("partner_id", "=", self.partner_id.id),
                    ("company_id", "=", self.env.company.id),
                ],
                limit=1,
            )
        )
        if person:
            person.user_id = self
            return
        self.env["hr.employee"].create(
            dict(
                name=self.name,
                company_id=self.env.company.id,
                **self.env["hr.employee"]._sync_user(self),
            )
        )

    def action_view_employees(self) -> dict:
        self.check_singleton()
        employees = self.employee_ids
        model = "hr.employee"
        if len(employees) > 1:
            return {
                "name": self.env._("Related Employees"),
                "type": "ir.actions.act_window",
                "res_model": model,
                "view_mode": "kanban,list,form",
                "domain": [("id", "in", employees.ids)],
            }
        return {
            "name": self.env._("Employee"),
            "type": "ir.actions.act_window",
            "res_model": model,
            "res_id": employees.id,
            "view_mode": "form",
        }

    def action_view_related_contact(self) -> dict:
        return {
            "name": self.env._("Related Contact"),
            "res_id": self.partner_id.id,
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "view_mode": "form",
        }

    def get_formview_action(self, access_uid=None):
        res = super().get_formview_action(access_uid=access_uid)
        user = self.env.user
        if access_uid:
            user = self.env["res.users"].browse(access_uid).sudo()

        if self.env.context.get("default_create_employee_id") and user.has_group(
            "base.group_erp_manager"
        ):
            res["views"] = [(self.env.ref("base.view_users_form").id, "form")]

        return res

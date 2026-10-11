import re
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from random import choice
from string import digits

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import Command, api, fields, models, tools
from odoo.exceptions import AccessError, RedirectWarning, UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.datetime import localize_standard, timezone
from odoo.libs.debug_log import DebugLog
from odoo.tools import (
    SQL,
    Query,
    convert,
    email_normalize,
    format_date,
    format_time,
    frozendict,
)

from odoo.addons.hr.models.hr_version import (
    _get_sorted_difference,
    format_date_abbr,
    remove_values_from_other_companies,
)
from odoo.addons.mail.tools.discuss import Store

_debug = DebugLog(__name__)

_ALLOW_READ_HR_EMPLOYEE = object()


def _searches_for_absence(operator, value) -> bool | None:
    if operator not in ("=", "!=", "in", "not in"):
        return None
    operands = (
        [value]
        if isinstance(value, str) or not hasattr(value, "__iter__")
        else list(value)
    )
    if not operands or any(operands):
        return None
    return operator in ("=", "in")


class HrEmployee(models.Model):
    _name = "hr.employee"
    _description = "Employee"
    _order = "name"
    _inherit = [
        "mixin.mail.thread.main.attachment",
        "mixin.mail.activity",
        "mixin.resource",
    ]
    _mail_post_access = "read"
    _primary_email = "work_email"
    _mail_partner_fields = ("partner_id",)
    _inherits = {"hr.version": "version_id", "res.partner": "partner_id"}

    _PUBLIC_PARTY_X2MANY_FIELDS = ("phone_ids",)

    _DIRTY_HACK_PRIVATE_FIELDS = (
        "activity_calendar_event_id",
        "rating_ids",
        "website_message_ids",
        "message_has_sms_error",
    )
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        tracking=True,
    )
    company_country_id = fields.Many2one(
        comodel_name="res.country",
        related="company_id.country_id",
        string="Company Country",
        readonly=True,
        groups="base.group_system,hr.group_hr_user",
    )
    company_country_code = fields.Char(
        related="company_country_id.code",
        string="Company Country Code",
        depends=["company_country_id"],
        readonly=True,
        groups="base.group_system,hr.group_hr_user",
    )
    country_code = fields.Char(
        related="version_id.country_code",
        inherited=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
        readonly=True,
        groups="hr.group_hr_user",
    )
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        required=True,
    )
    name = fields.Char(  # noqa: E8529 -- identity column of a delegated record: 33 files join hr_employee in raw SQL and read it, and it leads _order and name search
        related="partner_id.name",
        string="Employee Name",
        inherited=True,
        store=True,
        copy=True,
        readonly=False,
        tracking=True,
    )
    active = fields.Boolean(  # noqa: E8529 -- identity column of a delegated record: every search filters on it, 33 files join hr_employee in raw SQL
        related="resource_id.active",
        string="Active",
        default=True,
        store=True,
        readonly=False,
    )
    user_id = fields.Many2one(  # noqa: E8529 -- UNIQUE (user_id, company_id) partial
        comodel_name="res.users",
        related="resource_id.user_id",
        string="User",
        precompute=True,
        store=True,
        index="btree_not_null",
        copy=False,
        readonly=False,
        ondelete="restrict",
        check_company=True,
    )
    share = fields.Boolean(related="user_id.share")

    version_id = fields.Many2one(
        comodel_name="hr.version",
        compute="_compute_version_id",
        search="_search_version_id",
        compute_sudo=True,
        store=False,
        required=True,
        ondelete="cascade",
        value_sql="_version_id_sql",
    )
    resource_calendar_id = fields.Many2one(
        related="version_id.resource_calendar_id",
        inherited=True,
        store=False,
        index=False,
        check_company=True,
    )
    work_location_id = fields.Many2one(
        related="version_id.work_location_id",
        inherited=True,
        store=False,
        check_company=True,
    )
    current_version_id = fields.Many2one(
        comodel_name="hr.version",
        compute="_compute_current_version_id",
        compute_sudo=True,
        store=True,
        bypass_search_access=True,
    )
    current_date_version = fields.Date(
        related="current_version_id.date_version",
        string="Current Date Version",
        groups="hr.group_hr_user",
    )
    version_ids = fields.One2many(
        comodel_name="hr.version",
        inverse_name="employee_id",
        string="Employee Versions",
        groups="hr.group_hr_user",
    )
    first_contract_date = fields.Date(
        compute="_compute_first_contract_date",
        compute_sudo=True,
        store=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
        help="Start of the employee's current, unbroken occupation in this "
        "company. A gap of four days or more between two versions starts a new "
        "occupation, so an earlier stint does not count towards it.",
    )
    versions_count = fields.Integer(
        compute="_compute_versions_count",
        groups="hr.group_hr_user",
    )

    resource_state = fields.Selection(
        selection=[
            ("draft", "Onboarding"),
            ("available", "Available"),
            ("in_service", "Working"),
            ("maintenance", "On Leave"),
            ("out_of_service", "Suspended"),
            ("disposed", "Departed"),
        ],
        string="Status",
        compute="_compute_resource_state",
        inverse="_inverse_resource_state",
        search="_search_resource_state",
        help="The resource's state in HR words: on leave is its maintenance.",
    )
    hr_presence_state = fields.Selection(
        selection=[
            ("present", "Present"),
            ("absent", "Absent"),
            ("archive", "Archived"),
            ("out_of_working_hour", "Off-Hours"),
        ],
        compute="_compute_hr_presence_state",
        compute_sudo=True,
    )
    last_activity = fields.Date(
        compute="_compute_last_activity_and_time",
        compute_sudo=True,
    )
    last_activity_time = fields.Char(
        compute="_compute_last_activity_and_time",
        compute_sudo=True,
    )
    hr_icon_display = fields.Selection(
        selection=[
            ("presence_present", "Present"),
            ("presence_out_of_working_hour", "Off-Hours"),
            ("presence_absent", "Absent"),
            ("presence_archive", "Archived"),
            ("presence_undetermined", "Undetermined"),
        ],
        compute="_compute_presence_icon",
        compute_sudo=True,
    )
    show_hr_icon_display = fields.Boolean(
        compute="_compute_presence_icon",
        compute_sudo=True,
    )
    newly_hired = fields.Boolean(
        compute="_compute_newly_hired",
        search="_search_newly_hired",
        compute_sudo=True,
    )

    work_email = fields.Char(
        compute="_compute_work_email",
        inverse="_inverse_work_email",
        search="_search_work_email",
        compute_sudo=True,
        readonly=False,
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contact",
        index=True,
        copy=False,
        required=True,
        ondelete="restrict",
    )
    legal_name = fields.Char(
        compute="_compute_legal_name",
        store=True,
        readonly=False,
        classification="hr.private",
    )
    is_user_active = fields.Boolean(
        related="user_id.active",
        string="User's active",
        groups="hr.group_hr_user",
    )
    private_phone_ids = fields.Many2many(
        related="private_address_id.phone_ids",
        string="Private Phone",
        readonly=False,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )
    private_email = fields.Char(
        related="private_address_id.email",
        string="Private Email",
        readonly=False,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )
    place_of_birth = fields.Char(
        related="private_address_id.place_of_birth",
        string="Place of Birth",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )
    nationality_country_id = fields.Many2one(
        comodel_name="res.country",
        string="Nationality",
        compute="_compute_nationality_country_id",
        inverse="_inverse_nationality_country_id",
        compute_sudo=True,
        readonly=False,
        tracking=True,
        classification="hr.private",
        groups="hr.group_hr_user",
        help="The first nationality the person holds. A rule about the citizens of a country reads every nationality they hold.",
    )
    nationality_country_ids = fields.Many2many(
        comodel_name="res.country",
        string="Current Nationalities",
        compute="_compute_nationality_country_ids",
        search="_search_nationality_country_ids",
        compute_sudo=True,
        classification="hr.private",
        groups="hr.group_hr_user",
    )
    nationality_ids = fields.One2many(
        related="private_address_id.nationality_ids",
        readonly=False,
        classification="hr.private",
        groups="hr.group_hr_user",
    )
    country_of_birth = fields.Many2one(
        comodel_name="res.country",
        related="private_address_id.country_of_birth",
        string="Country of Birth",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )
    birthday = fields.Date(
        related="private_address_id.birthdate",
        string="Birthday",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )
    birthday_public_display = fields.Boolean(
        string="Show to all employees",
        default=False,
        groups="hr.group_hr_user",
    )
    birthday_public_display_string = fields.Char(
        string="Public Date of Birth",
        compute="_compute_birthday_public_display_string",
        compute_sudo=True,
    )
    identification_id = fields.Char(
        string="Identification No",
        compute="_compute_identifiers",
        inverse="_inverse_identifiers",
        search="_search_identification_id",
        compute_sudo=True,
        tracking=True,
        classification="hr.private",
        help="Enter the employee's National Identification Number issued by the government (e.g., Aadhaar, SIN, NIN). This is used for official records and statutory compliance.",
    )
    ssnid = fields.Char(
        string="SSN No",
        compute="_compute_identifiers",
        inverse="_inverse_identifiers",
        search="_search_ssnid",
        compute_sudo=True,
        tracking=True,
        classification="hr.private",
        help="Social Security Number",
    )
    passport_id = fields.Char(
        string="Passport No",
        compute="_compute_identifiers",
        inverse="_inverse_identifiers",
        search="_search_passport_id",
        compute_sudo=True,
        tracking=True,
        classification="hr.private",
    )
    passport_expiration_date = fields.Date(
        compute="_compute_identifiers",
        inverse="_inverse_identifiers",
        search="_search_passport_expiration_date",
        compute_sudo=True,
        tracking=True,
        classification="hr.private",
    )
    sex = fields.Selection(
        related="private_address_id.gender",
        string="Legal Sex",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
        help="This is the legal sex recognized by the state.",
    )

    private_address_id = fields.Many2one(
        comodel_name="res.partner",
        compute="_compute_private_address_id",
        store=True,
        index="btree_not_null",
        copy=False,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
        help="The employee's home address, held as a private child of their "
        "work contact rather than as columns here.",
    )
    private_street = fields.Char(
        related="private_address_id.street",
        string="Private Street",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )
    private_street2 = fields.Char(
        related="private_address_id.street2",
        string="Private Street2",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )
    private_city = fields.Char(
        related="private_address_id.city",
        string="Private City",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )
    allowed_country_state_ids = fields.Many2many(
        comodel_name="res.country.state",
        compute="_compute_allowed_country_state_ids",
        groups="hr.group_hr_user",
    )
    private_state_id = fields.Many2one(
        comodel_name="res.country.state",
        related="private_address_id.state_id",
        string="Private State",
        readonly=False,
        domain="[('id', 'in', allowed_country_state_ids)]",
        tracking=True,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )
    private_zip = fields.Char(
        related="private_address_id.zip",
        string="Private Zip",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )
    private_country_id = fields.Many2one(
        comodel_name="res.country",
        related="private_address_id.country_id",
        string="Private Country",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )
    marital = fields.Selection(
        related="private_address_id.marital",
        string="Marital Status",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )
    spouse_complete_name = fields.Char(
        related="private_address_id.spouse_complete_name",
        string="Spouse Legal Name",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )
    spouse_birthdate = fields.Date(
        related="private_address_id.spouse_birthdate",
        string="Spouse Birthdate",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )
    children = fields.Integer(
        related="private_address_id.dependent_children",
        string="Number of Dependent Children",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )
    emergency_contact = fields.Char(
        tracking=True,
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )
    emergency_phone_ids = fields.Many2many(
        comodel_name="phone.number",
        relation="hr_employee_emergency_phone_number_rel",
        column1="employee_id",
        column2="phone_number_id",
        groups="hr.group_hr_user,hr.privilege_apply_employee_change",
    )

    distance_home_work = fields.Integer(
        string="Home-Work Distance",
        tracking=True,
        classification="hr.private",
    )
    km_home_work = fields.Integer(
        string="Home-Work Distance in Km",
        compute="_compute_km_home_work",
        inverse="_inverse_km_home_work",
        store=True,
        tracking=True,
        classification="hr.private",
    )
    distance_home_work_unit = fields.Selection(
        selection=[
            ("kilometers", "km"),
            ("miles", "mi"),
        ],
        string="Home-Work Distance unit",
        default="kilometers",
        required=True,
        tracking=True,
        classification="hr.private",
    )
    work_location_name = fields.Char(
        compute="_compute_work_location_name",
        compute_sudo=True,
    )
    work_location_type = fields.Selection(
        selection=[("home", "Home"), ("office", "Office"), ("other", "Other")],
        compute="_compute_work_location_type",
        compute_sudo=True,
        tracking=True,
    )

    salary_allocation_ids = fields.One2many(
        comodel_name="hr.employee.bank.allocation",
        inverse_name="employee_id",
        string="Salary Allocations",
        groups="hr.group_hr_user",
        help="Which bank accounts the salary is paid into, and in what share",
    )
    salary_bank_account_ids = fields.Many2many(
        comodel_name="res.partner.bank.account",
        string="Salary Bank Accounts",
        compute="_compute_salary_bank_account_ids",
        inverse="_inverse_salary_bank_account_ids",
        search="_search_salary_bank_account_ids",
        domain="[('partner_id', '=', partner_id), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        groups="hr.group_hr_user",
        help="Employee bank accounts to pay salaries",
    )
    is_trusted_bank_account = fields.Boolean(
        compute="_compute_is_trusted_bank_account",
        compute_sudo=True,
        groups="hr.group_hr_user",
    )
    primary_bank_account_id = fields.Many2one(
        comodel_name="res.partner.bank.account",
        compute="_compute_primary_bank_account_id",
        groups="hr.group_hr_user",
    )
    has_multiple_bank_accounts = fields.Boolean(
        compute="_compute_has_multiple_bank_accounts",
        classification="hr.private",
    )

    visa_no = fields.Char(
        tracking=True,
        classification="hr.private",
    )
    visa_expire = fields.Date(
        string="Visa Expiration Date",
        tracking=True,
        classification="hr.private",
    )
    permit_no = fields.Char(
        string="Work Permit No",
        tracking=True,
        classification="hr.private",
    )
    work_permit_expiration_date = fields.Date(
        tracking=True,
        classification="hr.private",
    )
    has_work_permit = fields.Binary(
        string="Work Permit",
        classification="hr.private",
    )
    work_permit_name = fields.Char(
        string="work_permit_name",
        compute="_compute_work_permit_name",
        classification="hr.private",
    )

    certificate = fields.Selection(
        related="private_address_id.education_certificate",
        string="Certificate Level",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )
    study_field = fields.Char(
        related="private_address_id.study_field",
        string="Field of Study",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )
    study_school = fields.Char(
        related="private_address_id.study_school",
        string="School",
        readonly=False,
        tracking=True,
        groups="hr.group_hr_user",
    )

    driving_license = fields.Binary(classification="hr.private")
    private_car_plate = fields.Char(
        classification="hr.private",
        help="If you have more than one car, just separate the plates by a space.",
    )

    parent_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Manager",
        index=True,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        tracking=True,
    )
    child_ids = fields.One2many(
        comodel_name="hr.employee",
        inverse_name="parent_id",
        string="Direct subordinates",
    )
    coach_id = fields.Many2one(
        comodel_name="hr.employee",
        compute="_compute_coach_id",
        store=True,
        readonly=False,
        domain="['|', ('company_id', '=', False), ('company_id', 'in', allowed_company_ids)]",
        help='Select the "Employee" who is the coach of this employee.\n'
        'The "Coach" has no specific rights or responsibilities by default.',
    )

    tag_ids = fields.Many2many(
        comodel_name="res.partner.tag",
        relation="employee_tag_rel",
        column1="employee_id",
        column2="tag_id",
        string="Tags",
        groups="hr.group_hr_user",
    )
    tz = fields.Selection(tracking=True)
    color = fields.Integer(
        string="Color Index",
        default=0,
    )
    is_manager = fields.Boolean(compute="_compute_is_manager")
    is_user = fields.Boolean(compute="_compute_is_user")
    barcode = fields.Char(
        string="Badge ID",
        compute="_compute_identifiers",
        inverse="_inverse_identifiers",
        search="_search_barcode",
        compute_sudo=True,
        classification="hr.private",
        help="ID used for employee identification.",
    )
    pin = fields.Char(
        string="PIN",
        copy=False,
        classification="hr.private",
        help="PIN used to Check In/Out in the Kiosk Mode of the Attendance application (if enabled in Configuration) and to change the cashier in the Point of Sale application.",
    )
    message_main_attachment_id = fields.Many2one(groups="hr.group_hr_user")
    id_card = fields.Binary(
        string="ID Card Copy",
        classification="hr.private",
    )
    related_partners_count = fields.Integer(
        compute="_compute_related_partners_count",
        groups="hr.group_hr_user",
    )
    employee_properties = fields.Properties(
        definition="company_id.employee_properties_definition",
        string="Employee Properties",
        precompute=False,
        groups="hr.group_hr_user",
    )

    activity_ids = fields.One2many(groups="hr.group_hr_user")
    activity_state = fields.Selection(groups="hr.group_hr_user")
    activity_user_id = fields.Many2one(groups="hr.group_hr_user")
    activity_type_id = fields.Many2one(groups="hr.group_hr_user")
    activity_type_icon = fields.Char(groups="hr.group_hr_user")
    activity_date_deadline = fields.Date(groups="hr.group_hr_user")
    my_activity_date_deadline = fields.Date(groups="hr.group_hr_user")
    activity_summary = fields.Char(groups="hr.group_hr_user")
    activity_exception_decoration = fields.Selection(groups="hr.group_hr_user")
    activity_exception_icon = fields.Char(groups="hr.group_hr_user")

    message_is_follower = fields.Boolean(groups="hr.group_hr_user")
    message_follower_ids = fields.One2many(groups="hr.group_hr_user")
    message_partner_ids = fields.Many2many(groups="hr.group_hr_user")
    message_ids = fields.One2many(groups="hr.group_hr_user")
    has_message = fields.Boolean(groups="hr.group_hr_user")
    message_needaction = fields.Boolean(groups="hr.group_hr_user")
    message_needaction_counter = fields.Integer(groups="hr.group_hr_user")
    message_has_error = fields.Boolean(groups="hr.group_hr_user")
    message_has_error_counter = fields.Integer(groups="hr.group_hr_user")
    message_attachment_count = fields.Integer(groups="hr.group_hr_user")

    _BARCODE_DRAW_ATTEMPTS = 32

    _user_uniq = models.UniqueIndex(
        "(user_id, company_id) WHERE user_id IS NOT NULL",
        "A user cannot be linked to multiple employees in the same company.",
    )
    _partner_company_uniq = models.UniqueIndex(
        "(partner_id, company_id)",
        "A person cannot be two employees of the same company.",
    )

    _EXPIRY_REQUIRES_ITS_DOCUMENT = {
        "visa_expire": "visa_no",
        "work_permit_expiration_date": "permit_no",
    }

    @api.constrains(
        "visa_expire", "visa_no", "work_permit_expiration_date", "permit_no"
    )
    def _check_expiry_has_its_document(self) -> None:
        for employee in self:
            for expiry, number in self._EXPIRY_REQUIRES_ITS_DOCUMENT.items():
                if employee[expiry] and not employee[number]:
                    raise ValidationError(
                        self.env._(
                            "%(expiry_label)s cannot be set without "
                            "%(number_label)s: an expiry date belongs to a "
                            "document, and there is no document to attach it to.",
                            expiry_label=self._fields[expiry].string,
                            number_label=self._fields[number].string,
                        )
                    )

    @api.constrains("barcode")
    def _check_barcode(self) -> None:
        for employee in self:
            if employee.barcode and not (
                re.match(r"^[A-Za-z0-9]+$", employee.barcode)
                and len(employee.barcode) <= 18
            ):
                raise ValidationError(
                    self.env._(
                        "The Badge ID must be alphanumeric without any accents and no longer than 18 characters."
                    )
                )

    @api.constrains("user_id", "partner_id")
    def _check_work_contact_is_the_user_partner(self) -> None:
        for employee in self:
            user_partner = employee.user_id.partner_id
            if user_partner and employee.partner_id != user_partner:
                raise ValidationError(
                    self.env._(
                        "%(employee)s is linked to user %(user)s, so their work "
                        "contact must be that user's contact, not %(contact)s.",
                        employee=employee.display_name,
                        user=employee.user_id.display_name,
                        contact=employee.partner_id.display_name,
                    )
                )

    @api.constrains("pin")
    def _check_pin(self) -> None:
        for employee in self:
            if employee.pin and not employee.pin.isdigit():
                raise ValidationError(
                    self.env._("The PIN must be a sequence of digits.")
                )

    @api.model
    def new(self, values=None, origin=None, ref=None):
        if not values:
            values = {}
        new_vals, version_vals = self._split_employee_and_version_vals(values)
        _debug.lifecycle(
            "new",
            employee_keys=sorted(new_vals),
            version_keys=sorted(version_vals),
            origin=origin,
        )

        employee = super().new(new_vals, origin, ref)
        version_vals["employee_id"] = employee
        self.env["hr.version"].new(
            {
                f_name: value
                for f_name, value in version_vals.items()
                if self.env["hr.version"]._has_field_access(
                    self.env["hr.version"]._fields[f_name], "read"
                )
            }
        )
        return employee

    @api.model
    def _follow_company_calendar(self, company_id, vals_list) -> None:
        default_calendar = self.env.company.resource_calendar_id
        if company_id == self.env.company.id or not default_calendar.company_id:
            _debug.logic(
                "company_calendar_kept",
                company=company_id,
                calendar=default_calendar.id,
                reason="same_company_or_shared",
            )
            return
        company = self.env["res.company"].browse(company_id)
        for vals in vals_list:
            if (
                vals.get("resource_calendar_id", default_calendar.id)
                == default_calendar.id
            ):
                vals["resource_calendar_id"] = company.resource_calendar_id.id
                _debug.logic(
                    "company_calendar_followed",
                    old_calendar=default_calendar.id,
                    new_calendar=company.resource_calendar_id.id,
                    company=company_id,
                )

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({k for vals in vals_list for k in vals}),
                salary_simulation=bool(self.env.context.get("salary_simulation")),
            )
        vals_per_company = defaultdict(list)
        private_address_vals = {}
        for idx, caller_vals in enumerate(vals_list):
            vals, address_vals = self._split_private_address_vals(caller_vals)
            if address_vals:
                private_address_vals[idx] = address_vals
                _debug.logic(
                    "private_address_split", index=idx, keys=sorted(address_vals)
                )
            if vals.get("resource_id"):
                resource = self.env["resource.resource"].browse(vals["resource_id"])
                if "user_id" not in vals and resource.user_id:
                    vals["user_id"] = resource.user_id.id
                if not vals.get("partner_id") and resource.partner_id:
                    vals["partner_id"] = resource.partner_id.id
                if "name" not in vals and not vals.get("partner_id"):
                    vals["name"] = resource.name
                _debug.logic(
                    "resource_given",
                    index=idx,
                    resource=resource.id,
                    user=vals.get("user_id"),
                    name=vals.get("name"),
                )
            if vals.get("user_id"):
                user = self.env["res.users"].browse(vals["user_id"])
                vals.update(self._sync_user(user))
                vals["name"] = vals.get("name", user.name)
                _debug.pipeline(
                    "user_to_employee_vals",
                    user=user.id,
                    partner=vals.get("partner_id"),
                    name=vals.get("name"),
                )
            vals_per_company[vals.get("company_id") or self.env.company.id].append(
                (idx, vals)
            )
        index_per_employee = {}
        party_tz = {}
        for company_vals_list in vals_per_company.values():
            for idx, vals in company_vals_list:
                if vals.get("tz"):
                    party_tz[idx] = vals["tz"]
        employees = self.env["hr.employee"]
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "create_company_batches",
                batches=len(vals_per_company),
                sizes={c: len(batch) for c, batch in vals_per_company.items()},
            )
        for company, company_vals_list in vals_per_company.items():
            idxs, company_vals_list = zip(*company_vals_list, strict=True)
            self._update_party_vals(company, company_vals_list)
            self._follow_company_calendar(company, company_vals_list)
            with _debug.perf("create_super", cr=self.env.cr, company=company):
                new_employees = super(HrEmployee, self.with_company(company)).create(
                    company_vals_list
                )
            _debug.pipeline(
                "company_batch_created", company=company, employees=new_employees
            )
            index_per_employee.update(dict(zip(new_employees, idxs, strict=True)))
            employees |= new_employees
        employees = employees.sorted(key=lambda employee: index_per_employee[employee])
        employees._bind_resource_to_party()
        for employee in employees:
            idx = index_per_employee[employee]
            if address_vals := private_address_vals.get(idx):
                _debug.pipeline(
                    "private_address_written",
                    employee=employee.id,
                    keys=sorted(address_vals),
                )
                employee.write(address_vals)
            tz = party_tz.get(idx)
            if tz and employee.partner_id and not employee.partner_id.tz:
                employee.partner_id.sudo().tz = tz
                _debug.logic(
                    "party_tz_set",
                    employee=employee.id,
                    partner=employee.partner_id.id,
                    tz=tz,
                )
        employees.version_id._check_fields(["employee_id"])
        if self.env.context.get("salary_simulation"):
            _debug.lifecycle("create_done", employees=employees, salary_simulation=True)
            return employees
        employees.sudo()._update_missing_avatars()
        employee_departments = employees.department_id
        if employee_departments:
            channels = (
                self.env["discuss.channel"]
                .sudo()
                .search(
                    [("subscription_department_ids", "in", employee_departments.ids)]
                )
            )
            _debug.pipeline(
                "department_channels_resubscribed",
                departments=employee_departments,
                channels=channels,
            )
            channels._subscribe_users_automatically()
        onboarding_notes_bodies = {}
        hr_root_menu = self.env.ref("hr.menu_hr_root")
        for employee in employees:
            url = (
                "/odoo/%s/action-hr.plan_wizard_action?active_model=hr.employee&menu_id=%s"
                % (employee.id, hr_root_menu.id)
            )
            onboarding_notes_bodies[employee.id] = (
                Markup(
                    self.env._(
                        '<b>Congratulations!</b> May I recommend you to setup an <a href="%s">onboarding plan?</a>',
                    )
                )
                % url
            )
        employees._message_log_batch(onboarding_notes_bodies)
        employees.invalidate_recordset()
        _debug.lifecycle("create_done", employees=employees)
        return employees

    @api.model
    def _create(self, data_list):
        version_ids = [vals["stored"].pop("version_id", None) for vals in data_list]
        result = super()._create(data_list)
        pairs = [
            (version_id, employee.id)
            for version_id, employee in zip(version_ids, result, strict=True)
            if version_id
        ]
        if not pairs:
            _debug.pipeline("explicit_versions_bound", rows=len(data_list), bound=0)
            return result
        _debug.pipeline(
            "explicit_versions_bound",
            rows=len(data_list),
            bound=len(pairs),
            pairs=pairs,
        )
        explicit_version_fields = {
            version_id: set(vals["inherited"].get("hr.version", ()))
            for version_id, vals in zip(version_ids, data_list, strict=True)
            if version_id
        }
        versions = self.env["hr.version"].browse([pair[0] for pair in pairs])
        versions.flush_recordset()
        self.env.cr.execute(
            SQL(
                "UPDATE hr_version AS v SET employee_id = p.employee_id,"
                " write_date = %s, write_uid = %s"
                " FROM (VALUES %s) AS p(id, employee_id) WHERE v.id = p.id",
                fields.Datetime.now(),
                self.env.uid,
                SQL(", ").join(
                    SQL("(%s, %s)", version_id, employee_id)
                    for version_id, employee_id in pairs
                ),
            )
        )
        versions.invalidate_recordset(["employee_id", "write_date", "write_uid"])
        versions.modified(["employee_id"])
        for version in versions:
            for fname in explicit_version_fields[version.id]:
                field = version._fields[fname]
                if field.compute and field.store:
                    self.env.remove_to_compute(field, version)
                    _debug.logic("explicit_value_kept", version=version.id, field=fname)
        return result

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for vals in vals_list:
            if vals:
                vals.pop("employee_id", None)
        remove_values_from_other_companies(self, vals_list, default)
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "copy_data",
                employees=self,
                keys=sorted({k for vals in vals_list for k in vals}),
            )
        return vals_list

    @_debug.perf.timed
    def write(self, vals):
        vals = dict(vals)
        _debug.lifecycle("write", employees=self, keys=sorted(vals))
        if vals.get("company_id") and "resource_calendar_id" not in vals:
            company = self.env["res.company"].browse(vals["company_id"])
            moving = self.filtered(
                lambda employee: (
                    employee.resource_calendar_id.company_id
                    and employee.resource_calendar_id.company_id != company
                )
            )
            if moving:
                _debug.logic(
                    "write_company_calendar",
                    company=company.id,
                    calendar=company.resource_calendar_id.id,
                    moving=moving,
                    keeping=self - moving,
                )
                (self - moving).write(vals)
                moving.write(
                    {**vals, "resource_calendar_id": company.resource_calendar_id.id}
                )
                return True
        if "partner_id" in vals:
            _debug.pipeline(
                "party_changed",
                employees=self,
                partner=vals["partner_id"],
                unsubscribed=self.partner_id.ids,
            )
            self.message_unsubscribe(self.partner_id.ids)
        user_to_sync = None
        if "user_id" in vals:
            user_to_sync = self.env["res.users"].browse(vals["user_id"])
            vals.update(self._sync_user(user_to_sync))
            _debug.pipeline(
                "user_synced",
                user=user_to_sync.id,
                employees=self,
                partner=vals.get("partner_id"),
            )
        if vals.get("department_id") or vals.get("user_id"):
            department_ids = (
                [vals["department_id"]]
                if vals.get("department_id")
                else self.department_id.ids
            )
            if department_ids:
                channels = (
                    self.env["discuss.channel"]
                    .sudo()
                    .search([("subscription_department_ids", "in", department_ids)])
                )
                _debug.pipeline(
                    "department_channels_resubscribed",
                    departments=department_ids,
                    channels=channels,
                )
                channels._subscribe_users_automatically()
        if vals.get("departure_description"):
            _debug.lifecycle("departure_description_posted", employees=self)
            for employee in self:
                employee.message_post(
                    body=self.env._(
                        "Additional Information: \n %(description)s",
                        description=vals.get("departure_description"),
                    )
                )
        vals, address_vals = self._split_private_address_vals(vals)
        new_vals, version_vals = self._split_employee_and_version_vals(vals)
        _debug.logic(
            "write_split",
            employees=self,
            employee_keys=sorted(new_vals),
            version_keys=sorted(version_vals),
            address_keys=sorted(address_vals),
        )
        former_parties = {employee: employee.partner_id for employee in self}
        own_former_parties = {
            employee: party
            for employee, party in former_parties.items()
            if "partner_id" in vals
            and party.sudo().with_context(active_test=False).employee_ids == employee
        }
        with _debug.perf("write_super", cr=self.env.cr, employees=self):
            res = super().write(new_vals)
        if "partner_id" in vals:
            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "party_follow_ups",
                    employees=self,
                    former={e.id: p.id for e, p in former_parties.items()},
                )
            self._update_bank_account_contact(vals["partner_id"])
            self._reparent_private_address()
            self._bind_resource_to_party()
            self._move_identifiers_to_party(own_former_parties)
            self._retire_former_party(own_former_parties)
        if version_vals:
            version_vals["last_modified_date"] = fields.Datetime.now()
            version_vals["last_modified_uid"] = self.env.uid
            _debug.pipeline(
                "version_written",
                employees=self,
                version=self.version_id,
                keys=sorted(version_vals),
            )
            self.version_id.write(version_vals)

            for employee in self:
                employee._track_set_log_message(
                    Markup("<b>Modified on the Version '%s'</b>")
                    % employee.version_id.display_name
                )
        if address_vals:
            self._write_private_address(address_vals)
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_change_request_reviewed(self):
        reviewed = (
            self.env["hr.employee.change.request"]
            .search([("employee_id", "in", self.ids)])
            .filtered(lambda change: change.approval_state in ("new", "pending"))
        )
        if reviewed:
            raise UserError(
                self.env._(
                    "Cannot delete %(employees)s: a change request is being "
                    "reviewed. Refuse or cancel its approval first.",
                    employees=", ".join(reviewed.employee_id.mapped("name")),
                )
            )

    @api.model
    def _selection_installed_langs(self):
        return self.env["res.lang"].get_installed()

    @api.model
    def _is_version_delegate_field(self, fname) -> bool:
        field = self._fields.get(fname)
        return bool(
            field and field.inherited and field.related_field.model_name == "hr.version"
        )

    @api.model
    def _is_private_address_field(self, fname) -> bool:
        field = self._fields.get(fname)
        return bool(
            field and field.related and field.related.startswith("private_address_id.")
        )

    @api.model
    def _split_private_address_vals(self, vals) -> tuple:
        employee_vals, address_vals = {}, {}
        for fname, value in vals.items():
            target = (
                address_vals if self._is_private_address_field(fname) else employee_vals
            )
            target[fname] = value
        return employee_vals, address_vals

    def _write_private_address(self, address_vals) -> None:
        _debug.pipeline(
            "private_address_written",
            employees=self,
            keys=sorted(address_vals),
            sudo=True,
        )
        self._write_check_field_access(address_vals)
        super(HrEmployee, self.sudo()).write(address_vals)

    def _create_parent_records(self, data_list) -> None:
        Party = self.env["res.partner"].sudo()
        party_vals_list = [
            data["inherited"].pop("res.partner", {}) for data in data_list
        ]
        to_create = []
        for data, party_vals in zip(data_list, party_vals_list, strict=True):
            if partner_id := data["stored"].get("partner_id"):
                if party_vals:
                    Party.browse(partner_id).write(party_vals)
            else:
                to_create.append((data, party_vals))
        if to_create:
            parties = Party.create([party_vals for _data, party_vals in to_create])
            for party, (data, _party_vals) in zip(parties, to_create, strict=True):
                data["stored"]["partner_id"] = party.id
            _debug.pipeline("parties_created", parties=parties)
        _debug.pipeline(
            "parent_records_prepared",
            rows=len(data_list),
            new_parties=len(to_create),
            given=len(data_list) - len(to_create),
        )
        super()._create_parent_records(data_list)
        for data, party_vals in zip(data_list, party_vals_list, strict=True):
            if party_vals:
                data["inherited"]["res.partner"] = party_vals

    @api.model
    def _split_employee_and_version_vals(self, vals) -> tuple:
        employee_vals, version_vals = {}, {}
        for fname, value in vals.items():
            target = (
                version_vals
                if self._is_version_delegate_field(fname)
                else employee_vals
            )
            target[fname] = value
        return employee_vals, version_vals

    def _prepare_create_values(self, vals_list):
        result = super()._prepare_create_values(vals_list)
        new_vals_list = []
        Version = self.env["hr.version"]
        writable_version_fields = {
            fname
            for fname, field in Version._fields.items()
            if Version._has_field_access(field, "write")
        }
        for vals in result:
            employee_vals, version_vals = self._split_employee_and_version_vals(vals)
            if _debug.logic.enabled:
                _debug.logic(
                    "unwritable_version_keys_dropped",
                    keys=_get_sorted_difference(version_vals, writable_version_fields),
                )
            new_vals_list.append(
                {
                    **employee_vals,
                    **{
                        k: v
                        for k, v in version_vals.items()
                        if k in writable_version_fields
                    },
                }
            )
        return new_vals_list

    def _compute_salary_bank_account_ids(self) -> None:
        for employee in self:
            accounts = employee.salary_allocation_ids.bank_account_id
            employee.salary_bank_account_ids = accounts._filtered_access("read")

    def _search_salary_bank_account_ids(self, operator, value) -> list:
        allocations = self.env["hr.employee.bank.allocation"].sudo()
        return [
            (
                "id",
                "in",
                allocations.search(
                    [("bank_account_id", operator, value)]
                ).employee_id.ids,
            )
        ]

    def _inverse_salary_bank_account_ids(self) -> None:
        Allocation = self.env["hr.employee.bank.allocation"]
        for employee in self:
            wanted = employee.salary_bank_account_ids
            drafts = wanted.filtered(lambda account: not account.id)
            if drafts:
                wanted -= drafts
                wanted |= self.env["res.partner.bank.account"].create(
                    [draft._convert_to_write(draft._cache) for draft in drafts]
                )
            current = employee.salary_allocation_ids
            by_account = {a.bank_account_id.id: a.id for a in current}
            kept = current.browse(
                [by_account[i] for i in wanted.ids if i in by_account]
            )
            visible = current.bank_account_id._filtered_access("read")
            removed = (current - kept).filtered_domain(
                [("bank_account_id", "in", visible.ids)]
            )
            added = wanted - kept.mapped("bank_account_id")

            freed = sum(removed.filtered("amount_is_percentage").mapped("amount"))
            removed.unlink()

            ordered = kept.sorted(
                key=lambda a: (not a.amount_is_percentage, a.sequence)
            )
            if freed and ordered and ordered[0].amount_is_percentage:
                ordered[0].amount = employee.currency_id.round(
                    ordered[0].amount + freed
                )
                _debug.logic(
                    "salary_allocation_folded",
                    employee=employee.id,
                    percentage=freed,
                    account=ordered[0].bank_account_id.id,
                )

            if not added:
                continue
            allocated = sum(kept.filtered("amount_is_percentage").mapped("amount"))
            remaining = max(0.0, 100.0 - allocated)
            sequence = max(kept.mapped("sequence"), default=0)
            share = employee.currency_id.round(remaining / len(added))
            rows = []
            for index, account in enumerate(added.sorted("id")):
                sequence += 1
                amount = (
                    employee.currency_id.round(remaining)
                    if index == len(added) - 1
                    else share
                )
                rows.append(
                    {
                        "employee_id": employee.id,
                        "bank_account_id": account.id,
                        "sequence": sequence,
                        "amount": amount,
                        "amount_is_percentage": True,
                    }
                )
                remaining -= amount
            Allocation.create(rows)
            _debug.logic(
                "salary_allocation",
                employee=employee.id,
                added=added,
                removed=removed,
                kept=kept,
            )

    @api.depends(
        "salary_bank_account_ids.allow_out_payment",
        "salary_allocation_ids.amount",
    )
    def _compute_is_trusted_bank_account(self) -> None:
        for employee in self:
            employee.is_trusted_bank_account = (
                employee.primary_bank_account_id.allow_out_payment
            )

    @api.depends("salary_bank_account_ids")
    def _compute_has_multiple_bank_accounts(self) -> None:
        for employee in self:
            employee.has_multiple_bank_accounts = (
                len(employee.salary_bank_account_ids) > 1
            )

    @api.depends("private_country_id")
    def _compute_allowed_country_state_ids(self) -> None:
        states = None
        for employee in self:
            if employee.private_country_id:
                employee.allowed_country_state_ids = (
                    employee.private_country_id.state_ids
                )
            else:
                if states is None:
                    states = self.env["res.country.state"].search([])  # noqa: E8507 -- computed once, on first need
                employee.allowed_country_state_ids = states

    @api.depends("distance_home_work", "distance_home_work_unit")
    def _compute_km_home_work(self) -> None:
        for employee in self:
            employee.km_home_work = (
                employee.distance_home_work * 1.609
                if employee.distance_home_work_unit == "miles"
                else employee.distance_home_work
            )

    @api.depends(lambda self: [self._get_new_hire_field_name()])
    def _compute_newly_hired(self) -> None:
        new_hire_field = self._get_new_hire_field_name()
        new_hire_date = fields.Datetime.now() - timedelta(days=90)
        for employee in self:
            if not employee[new_hire_field]:
                employee.newly_hired = False
            elif not isinstance(employee[new_hire_field], datetime):
                employee.newly_hired = employee[new_hire_field] > new_hire_date.date()
            else:
                employee.newly_hired = employee[new_hire_field] > new_hire_date

    @api.depends("resource_calendar_id", "hr_presence_state")
    def _compute_presence_icon(self):
        for employee in self:
            employee.hr_icon_display = "presence_" + employee.hr_presence_state
            employee.show_hr_icon_display = bool(employee.user_id)

    @api.depends("name")
    def _compute_legal_name(self) -> None:
        for employee in self:
            if not employee.legal_name:
                employee.legal_name = employee.name

    @api.depends("current_version_id")
    @api.depends_context("version_id")
    def _compute_version_id(self) -> None:
        context_version_id = self.env.context.get("version_id", False)
        context_version = (
            self.env["hr.version"].browse(context_version_id).exists()
            if context_version_id
            else self.env["hr.version"]
        )

        _debug.logic(
            "version_from_context",
            employees=self,
            context_version_id=context_version_id,
            version=context_version,
        )
        for employee in self:
            if context_version and context_version.employee_id == employee:
                version = context_version
            else:
                version = employee.current_version_id
            employee.version_id = version

    @api.depends("version_id.work_location_id.name")
    def _compute_work_location_name(self) -> None:
        for employee in self:
            employee.work_location_name = (
                employee.version_id.work_location_id.name or None
            )

    @api.depends("version_id.work_location_id.location_type")
    def _compute_work_location_type(self) -> None:
        for employee in self:
            employee.work_location_type = (
                employee.version_id.work_location_id.location_type or "other"
            )

    @_debug.perf.timed
    @api.depends("version_ids.date_version", "version_ids.active", "active")
    def _compute_current_version_id(self) -> None:
        Version = self.env["hr.version"].with_context(active_test=True)
        today = fields.Date.today()
        latest_version_by_employee = {}
        for version in Version.search(
            [("employee_id", "in", self.ids), ("date_version", "<=", today)],
            order="date_version asc",
        ):
            latest_version_by_employee[version.employee_id.id] = version
        employees_without_past_version = [
            employee.id
            for employee in self
            if employee.id not in latest_version_by_employee
        ]
        earliest_version_by_employee = {}
        if employees_without_past_version:
            for version in Version.search(
                [("employee_id", "in", employees_without_past_version)],
                order="date_version asc",
            ):
                earliest_version_by_employee.setdefault(version.employee_id.id, version)
        no_version = self.env["hr.version"]
        _debug.logic(
            "current_version_computed",
            employees=self,
            with_past_version=len(latest_version_by_employee),
            earliest_fallback=len(earliest_version_by_employee),
        )
        changed = self.browse()
        for employee in self:
            new_current_version = latest_version_by_employee.get(
                employee.id
            ) or earliest_version_by_employee.get(employee.id, no_version)
            if not new_current_version and not employee.id:
                new_current_version = employee.version_ids[:1]
            if employee.current_version_id != new_current_version:
                _debug.lifecycle(
                    "current_version_changed",
                    employee=employee.id,
                    old_version=employee.current_version_id.id,
                    new_version=new_current_version.id,
                )
                employee.current_version_id = new_current_version
                changed |= employee
        changed._sync_resource_calendar_with_current_version()

    def _sync_resource_calendar_with_current_version(self) -> None:
        for employee in self.filtered("id"):
            resource = employee.resource_id
            version = employee.current_version_id
            calendar = version.resource_calendar_id
            if resource and version and resource.calendar_id != calendar:
                _debug.pipeline(
                    "resource_calendar_synced",
                    employee=employee.id,
                    resource=resource.id,
                    old_calendar=resource.calendar_id.id,
                    new_calendar=calendar.id,
                )
                resource.calendar_id = calendar

    @_debug.perf.timed
    @api.depends("partner_id")
    def _compute_private_address_id(self) -> None:
        Partner = self.env["res.partner"].sudo()
        unresolved = self.filtered(lambda e: not e.private_address_id)
        existing_by_contact = {}
        for home in Partner.search(
            [
                ("parent_id", "in", unresolved.partner_id.ids),
                ("type", "=", "private"),
            ],
            order="id",
        ):
            existing_by_contact.setdefault(home.parent_id, home)
        to_create = []
        for employee in unresolved:
            contact = employee.partner_id
            if not contact:
                employee.private_address_id = False
            elif contact in existing_by_contact:
                employee.private_address_id = existing_by_contact[contact]
            elif not employee.id:
                employee.private_address_id = employee._origin.private_address_id
            else:
                to_create.append(employee)
        _debug.logic(
            "private_address_resolved",
            employees=self,
            unresolved=len(unresolved),
            matched_homes=len(existing_by_contact),
            to_create=len(to_create),
        )
        if to_create:
            homes = Partner.create(
                [
                    {"parent_id": employee.partner_id.id, "type": "private"}
                    for employee in to_create
                ]
            )
            _debug.pipeline(
                "homes_created",
                homes=homes,
                employees=self.browse(e.id for e in to_create),
            )
            for employee, home in zip(to_create, homes, strict=True):
                employee.private_address_id = home

    @api.depends("parent_id")
    def _compute_coach_id(self) -> None:
        for version in self:
            manager = version.parent_id
            previous_manager = version._origin.parent_id
            if manager and (
                version.coach_id == previous_manager or not version.coach_id
            ):
                _debug.logic(
                    "coach_follows_manager",
                    version=version.id,
                    old_coach=version.coach_id.id,
                    manager=manager.id,
                )
                version.coach_id = manager
            elif not version.coach_id:
                version.coach_id = False

    @api.model
    def _access_field_class(self, field):
        if field.name in self._DIRTY_HACK_PRIVATE_FIELDS or (
            self._is_party_field(field.name)
            and not self._is_public_party_field(field.name)
        ):
            return "hr.employee_private"
        return super()._access_field_class(field)

    def check_no_existing_contract(self, date) -> None:
        if isinstance(date, str):
            date = fields.Date.from_string(date)
        if self._is_in_contract(date):
            raise ValidationError(
                self.env._(
                    "The employee is already in contract on %s. "
                    "Please select a date outside existing contracts",
                    format_date_abbr(self.env, date),
                )
            )

    @api.onchange("contract_template_id")
    def _onchange_contract_template_id(self) -> None:
        if self.contract_template_id:
            whitelist = self.env["hr.version"]._get_whitelist_fields_from_template()
            applied = []
            for field in self.contract_template_id._fields:
                if (
                    field in whitelist
                    and not self.env["hr.version"]._fields[field].related
                ):
                    self[field] = self.contract_template_id[field]
                    applied.append(field)
            _debug.logic(
                "contract_template_applied",
                employee=self._origin.id,
                template=self.contract_template_id.id,
                fields=applied,
            )

    @api.onchange("contract_date_start")
    def _onchange_contract_date_start(self) -> None:
        if not self.contract_date_start:
            self.contract_date_end = False

    @api.depends("partner_id.email")
    def _compute_work_email(self) -> None:
        for employee in self:
            employee.work_email = employee.partner_id.email

    def _search_work_email(self, operator, value):
        return Domain("partner_id.email", operator, value)

    def _inverse_work_email(self) -> None:
        for employee in self:
            employee.partner_id.sudo().email = employee.work_email

    def _inverse_km_home_work(self) -> None:
        for employee in self:
            employee.distance_home_work = (
                employee.km_home_work / 1.609
                if employee.distance_home_work_unit == "miles"
                else employee.km_home_work
            )

    @api.constrains("ssnid")
    def _check_ssnid(self):
        pass

    @api.onchange("private_state_id")
    def _onchange_private_state_id(self) -> None:
        if self.private_state_id:
            self.private_country_id = self.private_state_id.country_id

    def _get_display_name_visible_ids(self) -> set[int]:
        if not self.env.user._is_internal():
            return super()._get_display_name_visible_ids()
        return set(self._ids)

    @api.model
    def _get_new_hire_field_name(self) -> str:
        return "create_date"

    @api.depends("version_ids.date_start", "version_ids.date_end")
    def _compute_first_contract_date(self) -> None:
        for employee in self:
            employee.first_contract_date = employee._get_first_version_date()

    def _get_first_versions(self):
        self.check_singleton()
        versions = self.version_ids
        if self.env.context.get("before_date"):
            versions = versions.filtered(
                lambda c: c.date_start <= self.env.context["before_date"]
            )
        return versions

    def _get_first_version_date(self, no_gap=True):
        self.check_singleton()
        if not self.env.su and not self.env.user.has_group("hr.group_hr_user"):
            raise AccessError(
                self.env._(
                    "Only HR users can access first version date on an employee."
                )
            )

        def get_versions_continuous(versions):
            if not versions:
                return self.env["hr.version"]
            if len(versions) == 1:
                return versions
            current_version = versions[0]
            older_versions = versions[1:]
            current_date = current_version.date_start
            for i, other_version in enumerate(older_versions):
                gap = (current_date - (other_version.date_end or date(2100, 1, 1))).days
                current_date = other_version.date_start
                if gap >= 4:
                    _debug.logic(
                        "version_chain_gap",
                        employee=self.id,
                        before=other_version.id,
                        gap_days=gap,
                    )
                    return older_versions[0:i] + current_version
            return older_versions + current_version

        versions = self._get_first_versions().sorted("date_start", reverse=True)
        if no_gap:
            versions = get_versions_continuous(versions)
        return min(versions.mapped("date_start")) if versions else False

    @_debug.perf.timed
    def _cron_update_current_version_id(self) -> None:
        employees = self.with_context(active_test=False).search([])
        _debug.lifecycle("cron_update_current_version_start", employees=len(employees))
        employees._apply_pending_version_vals()
        employees._compute_current_version_id()
        _debug.lifecycle("cron_update_current_version_done")

    @_debug.perf.timed
    def _apply_pending_version_vals(self) -> None:
        due = (
            self.env["hr.version"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", self.ids),
                    ("pending_employee_vals", "!=", False),
                    ("date_version", "<=", fields.Date.today()),
                ],
                order="date_version asc, id asc",
            )
        )
        _debug.pipeline("pending_version_vals_due", count=len(due), versions=due)
        for version in due:
            vals = version.pending_employee_vals
            version.pending_employee_vals = False
            _debug.pipeline(
                "pending_version_vals_applied",
                version=version.id,
                keys=sorted(vals),
                employee=version.employee_id.id,
            )
            version.employee_id.sudo().write(vals)

    def _search_version_id(self, operator, value):
        if operator in ("any", "any!"):
            return Domain("current_version_id", operator, value)
        domain = Domain("id", operator, value)
        return Domain(
            "id", "in", self.env["hr.version"]._search(domain).select("employee_id")
        )

    def _version_id_sql(self, field, alias: str, query: (Query | None) = None) -> SQL:
        return self._field_to_sql(alias, "current_version_id", query)

    def _get_version(self, date=None):
        date = date or fields.Date.today()
        self.check_singleton()
        versions = self.version_ids.filtered_domain([("date_version", "<=", date)])
        return (
            max(versions, key=lambda v: v.date_version)
            if versions
            else self.version_ids[0]
        )

    @staticmethod
    def _coerce_date(value):
        if isinstance(value, str):
            return fields.Date.to_date(value)
        if isinstance(value, datetime):
            return value.date()
        return value

    def _get_new_version_dates(self, values) -> tuple:
        date = self._coerce_date(values.get("date_version", False))
        if not date:
            raise ValueError("date_version is required")

        date_from, date_to = self.sudo()._get_contract_dates(date)
        contract_date_start = self._coerce_date(
            values.get("contract_date_start", date_from)
        )
        contract_date_end = self._coerce_date(values.get("contract_date_end", date_to))

        if contract_date_end and not contract_date_start:
            raise UserError(
                self.env._("A contract end date requires a contract start date.")
            )
        _debug.logic(
            "new_version_dates",
            employee=self.id,
            date=date,
            contract_start=contract_date_start,
            contract_end=contract_date_end,
            existing_start=date_from,
            existing_end=date_to,
        )
        return date, contract_date_start, contract_date_end, date_from, date_to

    def _update_sibling_contract_end(
        self, employee_id, date_from, date_to, contract_date_start, contract_date_end
    ) -> None:
        if not (
            date_from
            and contract_date_start == date_from
            and contract_date_end != date_to
        ):
            _debug.logic(
                "sibling_contract_end",
                action="untouched",
                employee=employee_id,
                date_from=date_from,
                contract_start=contract_date_start,
                contract_end=contract_date_end,
                date_to=date_to,
            )
            return
        versions_sudo_to_sync = (
            self.env["hr.version"]
            .with_context(sync_contract_dates=True)
            .sudo()
            .search(
                [
                    ("employee_id", "=", employee_id),
                    ("contract_date_start", "=", date_from),
                ]
            )
        )
        if versions_sudo_to_sync:
            _debug.pipeline(
                "sibling_contract_end",
                action="synced",
                employee=employee_id,
                old_end=date_to,
                new_end=contract_date_end,
                versions=versions_sudo_to_sync,
            )
            versions_sudo_to_sync.write({"contract_date_end": contract_date_end})

    @_debug.perf.timed
    def create_version(self, values):
        self.check_singleton()
        _debug.lifecycle("create_version", employee=self.id, keys=sorted(values))
        date, contract_date_start, contract_date_end, date_from, date_to = (
            self._get_new_version_dates(values)
        )

        version_to_copy = self._get_version(date)
        if not version_to_copy:
            version_to_copy = self.env["hr.version"].search(
                [("employee_id", "=", self.id)], limit=1
            )
        if version_to_copy.date_version == date:
            _debug.logic(
                "version_reused",
                employee=self.id,
                version=version_to_copy.id,
                date=date,
            )
            return version_to_copy
        _debug.pipeline(
            "version_copied",
            employee=self.id,
            source_version=version_to_copy.id,
            source_date=version_to_copy.date_version,
            date=date,
        )

        employee_id = values.get("employee_id", self.id)
        self._update_sibling_contract_end(
            employee_id, date_from, date_to, contract_date_start, contract_date_end
        )
        self.check_access("write")
        version_to_copy.check_access("write")
        copy_vals = {
            "date_version": date,
            "employee_id": employee_id,
            "contract_date_start": contract_date_start,
            "contract_date_end": contract_date_end,
        }
        if "active" in values:
            copy_vals["active"] = values["active"]
        if calendar_id := values.get("resource_calendar_id"):
            copy_vals["resource_calendar_id"] = calendar_id
        new_version_vals = {
            field_name: field_value
            for field_name, field_value in values.items()
            if field_name not in copy_vals
        }
        version_fields = self.env["hr.version"]._fields
        employee_vals = {
            name: value
            for name, value in new_version_vals.items()
            if name not in version_fields
        }
        if employee_vals:
            if date <= fields.Date.today():
                _debug.pipeline(
                    "version_employee_vals",
                    employee=self.id,
                    keys=sorted(employee_vals),
                    mode="now",
                )
                self.write(employee_vals)
            else:
                _debug.pipeline(
                    "version_employee_vals",
                    employee=self.id,
                    keys=sorted(employee_vals),
                    mode="deferred",
                    date=date,
                )
                copy_vals["pending_employee_vals"] = employee_vals
            new_version_vals = {
                name: value
                for name, value in new_version_vals.items()
                if name in version_fields
            }
        copy_vals = {
            k: v
            for k, v in version_to_copy.sudo().copy_data()[0].items()
            if not (
                k in new_version_vals
                and version_fields[k].type in ["one2many", "many2many"]
            )
        } | copy_vals
        new_version = self.env["hr.version"].sudo().create(copy_vals).sudo(False)
        with self.env.protecting(
            [
                f
                for f_name, f in version_fields.items()
                if f_name not in new_version_vals and f.copy
            ],
            new_version,
        ):
            properties_fields_vals = {
                field_name: field_value
                for field_name, field_value in copy_vals.items()
                if version_fields[field_name].type == "properties"
                and field_name not in new_version_vals
            }
            if properties_fields_vals:
                new_version.sudo().write(properties_fields_vals)
            new_version.write(new_version_vals)
        _debug.lifecycle(
            "version_created",
            employee=self.id,
            version=new_version.id,
            keys=sorted(new_version_vals),
        )
        return new_version

    def create_contract(self, date):
        self.check_singleton()
        if date and isinstance(date, str):
            date = fields.Date.to_date(date)

        contracts = self._get_contract_versions(date)[self.id]
        future_contract_dates = [d for d in list(contracts.keys()) if d > date]
        new_contract_date_end = (
            min(future_contract_dates) + relativedelta(days=-1)
            if future_contract_dates
            else False
        )

        _debug.logic(
            "create_contract",
            employee=self.id,
            date=date,
            future_contracts=len(future_contract_dates),
            contract_end=new_contract_date_end,
        )
        if version_same_date := self.version_ids.filtered(
            lambda v: v.date_version == date
        ):
            _debug.pipeline(
                "contract_dates_on_existing_version",
                employee=self.id,
                version=version_same_date.id,
                date=date,
            )
            version_same_date.write(
                {
                    "contract_date_start": date,
                    "contract_date_end": new_contract_date_end,
                }
            )
            return version_same_date

        return self.create_version(
            {
                "date_version": date,
                "contract_date_start": date,
                "contract_date_end": new_contract_date_end,
            }
        )

    def _is_in_contract(self, date) -> bool:
        return self._get_contract_dates(date) != (False, False)

    def _get_contracts(self, date_start=None, date_end=None, domain=None):
        contract_versions_by_employee = self._get_contract_versions(
            date_start, date_end, domain
        )
        contracts_by_employee = defaultdict(lambda: self.env["hr.version"])
        for employee_id, versions_by_contract in contract_versions_by_employee.items():
            for contract_versions in versions_by_contract.values():
                if not date_end:
                    contracts_by_employee[employee_id] |= contract_versions[-1]
                    continue
                effective_versions = contract_versions.filtered(
                    lambda v, date_end=date_end: v.date_version <= date_end
                )
                contracts_by_employee[employee_id] |= (
                    effective_versions[-1]
                    if effective_versions
                    else contract_versions[0]
                )
        return contracts_by_employee

    @_debug.perf.timed
    def _get_contract_versions(self, date_start=None, date_end=None, domain=None):
        version_domain = Domain("contract_date_start", "!=", False)
        if self.ids:
            version_domain &= Domain("employee_id", "in", self.ids)
        elif not any(self._ids):
            version_domain &= Domain("employee_id", "in", self._origin.ids)
        if date_start:
            version_domain &= Domain("contract_date_end", "=", False) | Domain(
                "contract_date_end", ">=", date_start
            )
        if date_end:
            version_domain &= Domain("contract_date_start", "<=", date_end)
        if domain:
            version_domain &= domain
        all_versions = self.env["hr.version"]._read_group(
            domain=version_domain,
            groupby=["employee_id", "date_version:day"],
            aggregates=["id:recordset"],
        )
        contract_versions_by_employee = defaultdict(
            lambda: defaultdict(lambda: self.env["hr.version"])
        )
        for employee, _date_version, version in all_versions:
            first_version = next(iter(version), version)
            contract_versions_by_employee[employee.id][
                first_version.contract_date_start
            ] |= version
        _debug.logic(
            "contract_versions",
            employees=self,
            start=date_start,
            stop=date_end,
            employee_count=len(contract_versions_by_employee),
            contracts=sum(len(c) for c in contract_versions_by_employee.values()),
        )
        return contract_versions_by_employee

    def _get_all_contract_dates(self):
        self.check_singleton()
        return self.env["hr.version"]._read_group(
            [("employee_id", "=", self.id), ("contract_date_start", "!=", False)],
            ["contract_date_start:day", "contract_date_end:day"],
        )

    def _get_contract_dates(self, date) -> tuple:
        self.check_singleton()
        is_day_in_period = self.env["hr.version"]._is_day_in_period
        for date_from, date_to in self._get_all_contract_dates():
            if is_day_in_period(date_from, date_to, date):
                return date_from, date_to
        return False, False

    @api.depends("version_ids")
    def _compute_versions_count(self) -> None:
        version_count_per_employee = dict(
            self.env["hr.version"]._read_group(
                [("employee_id", "in", self.ids)],
                ["employee_id"],
                ["id:count"],
            ),
        )
        for employee in self:
            employee.versions_count = version_count_per_employee.get(employee, 0)

    def _search_newly_hired(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        new_hire_field = self._get_new_hire_field_name()
        threshold = fields.Datetime.now() - timedelta(days=90)
        if operator == "in":
            return Domain(new_hire_field, ">", threshold)
        return Domain(new_hire_field, "<=", threshold) | Domain(
            new_hire_field, "=", False
        )

    @api.model
    def _get_valid_employee_for_user(self):
        user = self.env.user
        employee = user.employee_id
        if not employee:
            user_employees = self.sudo().search([("user_id", "=", user.id)])
            employee = (
                user_employees.filtered(lambda r: r.company_id == user.company_id)
                or user_employees[:1]
            )
            _debug.logic(
                "employee_company_fallback",
                user=user.id,
                company=self.env.company.id,
                candidates=user_employees,
                employee=employee,
            )
        return employee

    @api.model
    def _search_member_of_department_domain(self, operator):
        if operator != "in":
            return NotImplemented
        department = self._get_valid_employee_for_user().department_id
        if not department:
            return Domain.FALSE
        return Domain("department_id", "child_of", department.ids)

    @api.model
    def _get_employee_ids_working_now(self):
        start_dt = fields.Datetime.now().replace(tzinfo=UTC)
        stop_dt = start_dt + timedelta(hours=1)
        employees_by_schedule = defaultdict(lambda: self.env["hr.employee"])
        for employee in self.sudo():
            if employee.contract_date_start and not employee.is_in_contract:
                continue
            employees_by_schedule[
                (employee.tz or "UTC", employee.resource_calendar_id)
            ] += employee
        working_now = []
        for (tz, calendar), employees in employees_by_schedule.items():
            if calendar.schedule_type == "fully_flexible":
                continue
            zone = timezone(tz)
            work_intervals = calendar._work_intervals_batch(
                start_dt.astimezone(zone), stop_dt.astimezone(zone)
            )[False]
            if work_intervals:
                working_now += employees.ids
        _debug.logic(
            "working_now",
            employees=self,
            schedule_groups=len(employees_by_schedule),
            working=len(working_now),
        )
        return working_now

    @api.depends(
        "private_address_id.nationality_ids.country_id",
        "private_address_id.nationality_ids.sequence",
        "private_address_id.nationality_ids.date_lost",
    )
    def _compute_nationality_country_ids(self) -> None:
        for employee in self:
            employee.nationality_country_ids = (
                employee.private_address_id.nationality_ids._filter_held().country_id
            )

    @api.depends(
        "private_address_id.nationality_ids.country_id",
        "private_address_id.nationality_ids.sequence",
        "private_address_id.nationality_ids.date_lost",
    )
    def _compute_nationality_country_id(self) -> None:
        for employee in self:
            employee.nationality_country_id = (
                employee.private_address_id.nationality_ids._filter_held()[
                    :1
                ].country_id
            )

    def _inverse_nationality_country_id(self) -> None:
        for employee in self:
            rows = employee.nationality_ids
            held = rows._filter_held()
            country = employee.nationality_country_id
            if not country:
                employee.nationality_ids = [
                    Command.update(
                        row.id, {"date_lost": fields.Date.context_today(self)}
                    )
                    for row in held
                ]
                continue
            first_sequence = min(held.mapped("sequence") or [10]) - 1
            first = rows.filtered(
                lambda row, country=country: row.country_id == country
            )
            if first:
                values = {"date_lost": False, "sequence": first_sequence}
                command = Command.update(first.id, values)
            elif held:
                command = Command.update(
                    held[:1].id,
                    {
                        "country_id": country.id,
                        "sequence": first_sequence,
                        "basis": False,
                        "date_acquired": False,
                        "identifier_id": False,
                        "partner_identifier_id": False,
                    },
                )
            else:
                command = Command.create({"country_id": country.id})
            employee.nationality_ids = [command]

    def _search_nationality_country_ids(self, operator, value):
        if operator not in ("in", "any"):
            return NotImplemented
        held = self.env["resource.nationality"]._get_held_domain()
        return [
            (
                "private_address_id.nationality_ids",
                "any",
                held & Domain("country_id", operator, value),
            )
        ]

    def _get_nationality_declared_to(self, country):
        self.check_singleton()
        if country in self.nationality_country_ids:
            return country
        return self.nationality_country_id

    @api.depends("resource_id.state")
    def _compute_resource_state(self) -> None:
        for employee in self:
            employee.resource_state = employee.resource_id.state

    def _inverse_resource_state(self) -> None:
        for state, employees in (
            self.filtered("resource_state").grouped("resource_state").items()
        ):
            employees.resource_id.write({"state": state})

    def _search_resource_state(self, operator, value):
        return [("resource_id.state", operator, value)]

    @_debug.perf.timed
    @api.depends("user_id.im_status", "active")
    def _compute_hr_presence_state(self) -> None:
        in_contract_ids = set(self.sudo().filtered("is_in_contract")._ids)
        employee_to_check_working = self.filtered(
            lambda e: (
                e.id in in_contract_ids
                and e.company_id.sudo().hr_config_id.hr_presence_control_login
                and (e.user_id.sudo().presence_ids.status or "offline") == "offline"
            )
        )
        working_now_list = employee_to_check_working._get_employee_ids_working_now()
        _debug.logic(
            "presence_login_control",
            employees=self,
            offline=len(employee_to_check_working),
            in_working_hours=len(working_now_list),
        )
        for employee in self:
            state = "out_of_working_hour"
            if (
                employee.id in in_contract_ids
                and employee.company_id.sudo().hr_config_id.hr_presence_control_login
            ):
                presence_status = (
                    employee.user_id.sudo().presence_ids.status or "offline"
                )
                if presence_status == "online":
                    state = "present"
                elif presence_status == "offline" and employee.id in working_now_list:
                    state = "absent"
            if not employee.active:
                state = "archive"
            employee.hr_presence_state = state

    @api.depends("user_id")
    def _compute_last_activity_and_time(self) -> None:
        for employee in self:
            tz = employee.tz
            if last_presence := employee.user_id.sudo().presence_ids.last_presence:
                last_activity_datetime = (
                    last_presence.replace(tzinfo=UTC)
                    .astimezone(timezone(tz or "UTC"))
                    .replace(tzinfo=None)
                )
                employee.last_activity = last_activity_datetime.date()
                if employee.last_activity == fields.Date.today():
                    employee.last_activity_time = format_time(
                        self.env, last_presence, time_format="short"
                    )
                else:
                    employee.last_activity_time = False
            else:
                employee.last_activity = False
                employee.last_activity_time = False

    @api.depends("birthday", "birthday_public_display")
    def _compute_birthday_public_display_string(self) -> None:
        for employee in self:
            if employee.birthday and employee.birthday_public_display:
                employee.birthday_public_display_string = format_date(
                    self.env, employee.birthday, date_format="dd MMMM"
                )
            else:
                employee.birthday_public_display_string = "hidden"

    @api.depends("name", "permit_no")
    def _compute_work_permit_name(self) -> None:
        for employee in self:
            name = employee.name.replace(" ", "_") + "_" if employee.name else ""
            permit_no = "_" + employee.permit_no if employee.permit_no else ""
            employee.work_permit_name = "%swork_permit%s" % (name, permit_no)

    def _get_partner_count_depends(self):
        return ["user_id", "partner_id"]

    @api.depends(lambda self: self._get_partner_count_depends())
    def _compute_related_partners_count(self) -> None:
        for employee in self:
            employee.related_partners_count = len(employee._get_related_partners())

    def _get_related_partners(self):
        return self.partner_id | self.user_id.partner_id

    def action_view_related_contacts(self):
        related_partners = self._get_related_partners()
        action = {
            "name": self.env._("Related Contacts"),
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "view_mode": "form",
        }
        if len(related_partners) > 1:
            action["view_mode"] = "kanban,list,form"
            action["domain"] = [("id", "in", related_partners.ids)]
            return action
        if not related_partners:
            raise UserError(self.env._("%s has no related contact.", self.display_name))
        action["res_id"] = related_partners.id
        return action

    def action_create_user(self) -> dict:
        self.check_singleton()
        if self.user_id:
            raise ValidationError(self.env._("This employee already has an user."))
        return {
            "name": self.env._("Create User"),
            "type": "ir.actions.act_window",
            "res_model": "res.users",
            "view_mode": "form",
            "view_id": self.env.ref("hr.view_users_simple_form").id,
            "target": "new",
            "context": {
                **self.env.context,
                "default_create_employee_id": self.id,
                "default_name": self.name,
                "default_login": self.work_email,
                "default_partner_id": self.partner_id.id,
            },
        }

    def action_create_users_confirmation(self) -> None:
        raise RedirectWarning(
            message=self.env._(
                "You're about to invite new users. %s users will be created with the default user template's rights. "
                "Adding new users may increase your subscription cost. Do you wish to continue?",
                len(self.ids),
            ),
            action=self.env.ref("hr.action_hr_employee_create_users").id,
            button_text=self.env._("Confirm"),
            additional_context={
                "selected_ids": self.ids,
            },
        )

    def _prepare_action_user_creation_notification(
        self, message, message_type, next_action
    ) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("User Creation Notification"),
                "type": message_type,
                "message": message,
                "next": next_action,
            },
        }

    def _prepare_user_vals_and_blocked_names(self) -> tuple:
        employee_emails = [
            normalized_email
            for employee in self
            for normalized_email in tools.mail.email_normalize_all(employee.work_email)
        ]
        conflicting_users = self.env["res.users"]
        if employee_emails:
            conflicting_users = self.env["res.users"].search(
                [
                    "|",
                    ("email_normalized", "in", employee_emails),
                    ("login", "in", employee_emails),
                ]
            )
        taken_addresses = set(conflicting_users.mapped("email_normalized")) | set(
            conflicting_users.mapped("login")
        )
        create_vals = []
        blocked = defaultdict(list)
        for employee in self:
            if employee.user_id:
                blocked["has_user"].append(employee.name)
                continue
            if not employee.work_email:
                blocked["no_email"].append(employee.name)
                continue
            login = email_normalize(employee.work_email)
            if not login:
                blocked["invalid_email"].append(employee.name)
                continue
            if login in taken_addresses:
                blocked["address_taken"].append(employee.name)
                continue
            create_vals.append(
                {
                    "create_employee_id": employee.id,
                    "name": employee.name,
                    "login": login,
                    "partner_id": employee.partner_id.id,
                }
            )
        if _debug.logic.enabled:
            _debug.logic(
                "user_vals_prepared",
                employees=self,
                creatable=len(create_vals),
                taken_addresses=len(taken_addresses),
                blocked={k: len(v) for k, v in blocked.items()},
            )
        return create_vals, blocked

    def action_create_users(self):
        create_vals, blocked = self._prepare_user_vals_and_blocked_names()

        next_action = {"type": "ir.actions.act_window_close"}
        if create_vals:
            _debug.pipeline(
                "users_created",
                employees=self,
                count=len(create_vals),
                employee_ids=[vals["create_employee_id"] for vals in create_vals],
            )
            self.env["res.users"].create(create_vals)
            next_action = self._prepare_action_user_creation_notification(
                self.env._(
                    "Users %s creation successful",
                    ", ".join(vals["name"] for vals in create_vals),
                ),
                "success",
                {
                    "type": "ir.actions.client",
                    "tag": "soft_reload",
                    "params": {"next": next_action},
                },
            )

        for names, message_type, message in (
            (
                blocked["has_user"],
                "warning",
                self.env._(
                    "User already exists for Those Employees %s",
                    ", ".join(blocked["has_user"]),
                ),
            ),
            (
                blocked["no_email"],
                "danger",
                self.env._(
                    "You need to set the work email address for %s",
                    ", ".join(blocked["no_email"]),
                ),
            ),
            (
                blocked["invalid_email"],
                "danger",
                self.env._(
                    "You need to set a valid work email address for %s",
                    ", ".join(blocked["invalid_email"]),
                ),
            ),
            (
                blocked["address_taken"],
                "warning",
                self.env._(
                    "User already exists with the same email for Employees %s",
                    ", ".join(blocked["address_taken"]),
                ),
            ),
        ):
            if names:
                next_action = self._prepare_action_user_creation_notification(
                    message, message_type, next_action
                )
        return next_action

    def _is_party_field(self, fname) -> bool:
        field = self._fields[fname]
        return bool(
            field.inherited and field.inherited_field.model_name == "res.partner"
        )

    def _is_public_party_field(self, fname):
        field = self._fields[fname]
        return self._is_party_field(fname) and (
            fname.startswith(("image_", "avatar_"))
            or fname in self._PUBLIC_PARTY_X2MANY_FIELDS
            or (
                field.inherited_field.store
                and field.inherited_field.type not in ("one2many", "many2many")
            )
        )

    @_debug.perf.timed
    @api.model
    def notify_expiring_contract_work_permit(self):
        _debug.lifecycle("cron_expiry_notification_start")
        companies = self.env["res.company"].search([])
        employees_contract_expiring = self.env["hr.employee"]
        employees_work_permit_expiring = self.env["hr.employee"]

        today = fields.Date.today()
        companies_by_contract_period = defaultdict(lambda: self.env["res.company"])
        companies_by_permit_period = defaultdict(lambda: self.env["res.company"])
        for company in companies:
            companies_by_contract_period[
                company.hr_config_id.contract_expiration_notice_period
            ] += company
            companies_by_permit_period[
                company.hr_config_id.work_permit_expiration_notice_period
            ] += company

        for notice_period, period_companies in companies_by_contract_period.items():
            employees_contract_expiring += self.env["hr.employee"].search(  # noqa: E8507 -- one query per distinct notice period; companies sharing one were merged above
                [
                    ("company_id", "in", period_companies.ids),
                    ("contract_date_start", "!=", False),
                    ("contract_date_start", "<=", today),
                    ("contract_date_end", ">=", today),
                    (
                        "contract_date_end",
                        "<=",
                        today + relativedelta(days=notice_period),
                    ),
                ]
            )
        for notice_period, period_companies in companies_by_permit_period.items():
            employees_work_permit_expiring += self.env["hr.employee"].search(  # noqa: E8507 -- one query per distinct notice period; companies sharing one were merged above
                [
                    ("company_id", "in", period_companies.ids),
                    ("work_permit_expiration_date", ">=", today),
                    (
                        "work_permit_expiration_date",
                        "<=",
                        today + relativedelta(days=notice_period),
                    ),
                ]
            )

        _debug.logic(
            "expiry_periods",
            companies=len(companies),
            contract_periods=len(companies_by_contract_period),
            permit_periods=len(companies_by_permit_period),
            contracts_expiring=employees_contract_expiring,
            permits_expiring=employees_work_permit_expiring,
        )
        for employee in employees_contract_expiring:
            employee._schedule_expiry_activity(
                employee.contract_date_end,
                self.env._("The contract of %s is about to expire.", employee.name),
            )

        for employee in employees_work_permit_expiring:
            employee._schedule_expiry_activity(
                employee.work_permit_expiration_date,
                self.env._("The work permit of %s is about to expire.", employee.name),
            )

        _debug.lifecycle("cron_expiry_notification_done")
        return True

    def _schedule_expiry_activity(self, date_deadline, summary) -> None:
        self.check_singleton()
        already_scheduled = (
            self.env["mail.activity"]
            .sudo()
            .search_count(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("date_deadline", "=", date_deadline),
                    ("summary", "=", summary),
                ],
                limit=1,
            )
        )
        if already_scheduled:
            _debug.logic(
                "expiry_activity_skipped",
                employee=self.id,
                deadline=date_deadline,
                reason="already_scheduled",
            )
            return
        _debug.pipeline(
            "expiry_activity_scheduled",
            employee=self.id,
            deadline=date_deadline,
            user=self.hr_responsible_id.id or self.env.uid,
        )
        self.with_context(mail_activity_quick_update=True).activity_schedule(
            "mail.mail_activity_data_todo",
            date_deadline,
            summary,
            user_id=self.hr_responsible_id.id or self.env.uid,
        )

    def _load_demo_data(self) -> dict | None:
        self.sudo()._load_scenario()
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    @api.onchange("user_id")
    def _onchange_user(self) -> None:
        self.update(self._sync_user(self.user_id))
        if not self.name:
            self.name = self.user_id.name

    @api.onchange("resource_calendar_id")
    def _onchange_timezone(self) -> None:
        if self.resource_calendar_id and not self.tz:
            self.tz = self.resource_calendar_id.tz

    @_debug.perf.timed
    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self._origin:
            return {
                "warning": {
                    "title": self.env._("Warning"),
                    "message": self.env._(
                        "To avoid multi company issues (losing the access to your previous contracts, leaves, ...), you should create another employee in the new company instead."
                    ),
                }
            }
        return None

    def _load_scenario(self) -> None:
        demo_tag = self.env.ref("hr.employee_category_demo", raise_if_not_found=False)
        if demo_tag:
            return
        convert.convert_file(
            self.env, "hr", "data/scenarios/hr_scenario.xml", None, mode="init"
        )

    @api.depends("salary_allocation_ids.sequence", "salary_bank_account_ids")
    def _compute_primary_bank_account_id(self) -> None:
        for employee in self:
            allocations = employee.salary_allocation_ids
            employee.primary_bank_account_id = (
                allocations[0].bank_account_id
                if allocations
                else employee.salary_bank_account_ids[:1]
            )

    def action_unarchive(self):
        _debug.lifecycle("unarchive_departure_cleared", employees=self)
        res = super().action_unarchive()
        self.write(
            {
                "departure_reason_id": False,
                "departure_description": False,
                "departure_date": False,
            }
        )
        return res

    @_debug.perf.timed
    def action_archive(self):
        archived_employees = self.filtered("active")
        _debug.lifecycle(
            "archive",
            employees=self,
            active=archived_employees,
            no_wizard=bool(self.env.context.get("no_wizard")),
        )
        res = super().action_archive()
        if archived_employees:
            employee_fields_to_empty = (
                self._get_employee_field_names_to_empty_on_archive()
            )
            user_fields_to_empty = self._get_user_field_names_to_empty_on_archive()
            employee_domain = Domain.OR(
                Domain(field, "in", archived_employees.ids)
                for field in employee_fields_to_empty
            )
            user_domain = Domain.OR(
                Domain(field, "in", archived_employees.user_id.ids)
                for field in user_fields_to_empty
            )
            employees = self.env["hr.employee"].search(employee_domain | user_domain)
            _debug.pipeline(
                "archive_fields_emptied",
                employee_fields=employee_fields_to_empty,
                user_fields=user_fields_to_empty,
                employees=employees,
            )
            for field in employee_fields_to_empty:
                employees.filtered_domain(
                    [(field, "in", archived_employees.ids)]
                ).write({field: False})
            for field in user_fields_to_empty:
                employees.filtered_domain(
                    [(field, "in", archived_employees.user_id.ids)]
                ).write({field: False})

            if len(archived_employees) == 1 and not self.env.context.get(
                "no_wizard", False
            ):
                _debug.logic("archive_departure_wizard", employee=archived_employees.id)
                return {
                    "type": "ir.actions.act_window",
                    "name": self.env._("Register Departure"),
                    "res_model": "wizard.hr.employee.register.departure",
                    "view_mode": "form",
                    "target": "new",
                    "context": {"active_id": archived_employees.id},
                    "views": [[False, "form"]],
                }
        return res

    def action_toggle_primary_bank_account_trust(self) -> None:
        self.check_singleton()
        current_val = self.primary_bank_account_id.allow_out_payment
        self.primary_bank_account_id.allow_out_payment = not current_val

    def action_view_allocation_wizard(self):
        self.check_singleton()
        wizard = self.env["wizard.hr.employee.update.bank.allocation"].create(
            {
                "employee_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Bank Account Allocation"),
            "res_model": "wizard.hr.employee.update.bank.allocation",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_view_versions(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.name + self.env._(" Records"),
            "path": "versions",
            "res_model": "hr.version",
            "view_mode": "list,graph,pivot",
            "views": [
                (self.env.ref("hr.hr_version_list_view").id, "list"),
                (False, "graph"),
                (False, "pivot"),
            ],
            "domain": [("employee_id", "=", self.id)],
            "search_view_id": self.env.ref("hr.hr_version_search_view").id,
        }

    def action_generate_random_barcode(self) -> None:
        Employee = self.env["hr.employee"].sudo().with_context(active_test=False)
        minted = set()
        for employee in self:
            for _attempt in range(self._BARCODE_DRAW_ATTEMPTS):
                barcode = "041" + "".join(choice(digits) for _ in range(9))
                if barcode in minted:
                    continue
                if not Employee.search_count([("barcode", "=", barcode)], limit=1):  # noqa: E8507 -- draws a random barcode until a free one turns up
                    break
            else:
                raise UserError(
                    self.env._(
                        "Could not generate a unique Badge ID after %(attempts)s"
                        " attempts. Please set one manually.",
                        attempts=self._BARCODE_DRAW_ATTEMPTS,
                    )
                )
            minted.add(barcode)
            _debug.logic("badge_minted", employee=employee.id, draws=_attempt + 1)
            employee.barcode = barcode

    def _get_schedule_tz(self):
        self.check_singleton()
        return (
            self.tz
            or self.resource_calendar_id.tz
            or self.company_id.resource_calendar_id.tz
            or "UTC"
        )

    def _get_schedule_tz_batch(self, dt=None):
        employees_by_id = self.grouped("id")

        def get_timezones_by_employee_id(employees, date_at=None):
            return {
                emp_id: employees_by_id[emp_id].tz or calendar.sudo().tz
                for emp_id, calendar in employees._get_calendars(date_at).items()
            }

        if not dt:
            return get_timezones_by_employee_id(self)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        employee_timezones = {}
        for tz, employees in self.grouped(lambda emp: emp._get_schedule_tz()).items():
            employee_timezones |= get_timezones_by_employee_id(
                employees, dt.astimezone(timezone(tz)).date()
            )
        return employee_timezones

    def _get_calendars(self, date_from=None):
        res = super()._get_calendars(date_from=date_from)
        if not date_from:
            return res

        date_from = fields.Date.to_date(date_from)
        for employee in self:
            employee_versions_sudo = employee.sudo().version_ids.filtered(
                lambda v: v._is_in_contract(date_from)
            )
            version_sudo = employee_versions_sudo[:1] or employee.sudo()._get_version(
                date_from
            )
            if version_sudo:
                res[employee.id] = version_sudo.resource_calendar_id.with_env(
                    employee.env
                )
                _debug.logic(
                    "calendar_from_version",
                    employee=employee.id,
                    date=date_from,
                    version=version_sudo.id,
                    source="in_contract" if employee_versions_sudo else "nearest",
                    calendar=version_sudo.resource_calendar_id.id,
                )
        return res

    @staticmethod
    def _combine_tz(day, moment, tz):
        naive = datetime.combine(day, moment)
        return localize_standard(naive, tz) if tz else naive

    @_debug.perf.timed
    def _get_version_periods(self, start, stop, field_name=None, check_contract=False):
        if field_name and field_name not in self.env["hr.version"]._fields:
            raise UserError(
                self.env._(
                    "This field %(field_name)s doesn't exist on this model (hr.version).",
                    field_name=field_name,
                )
            )
        version_periods_by_employee = defaultdict(list)
        if check_contract:
            versions = self._get_versions_with_contract_overlap_with_period(
                start.date(), stop.date()
            )
        else:
            start_date, stop_date = start.date(), stop.date()
            versions = self.version_ids.filtered(
                lambda version: (
                    version.date_start
                    and version.date_start <= stop_date
                    and (not version.date_end or version.date_end >= start_date)
                )
            )
        _debug.logic(
            "version_periods",
            employees=self,
            start=start,
            stop=stop,
            field=field_name,
            check_contract=check_contract,
            versions=versions,
        )
        for version in versions:
            calendar_tz = timezone(version.employee_id.resource_id.tz)
            date_start = self._combine_tz(
                version.date_start, time.min, calendar_tz
            ).astimezone(UTC)
            end_date = version.date_end
            if end_date:
                date_end = self._combine_tz(
                    end_date + relativedelta(days=1), time.min, calendar_tz
                ).astimezone(UTC)
            else:
                date_end = stop
            version_periods_by_employee[version.employee_id].append(
                (
                    max(date_start, start),
                    min(date_end, stop),
                    version[field_name] if field_name else version,
                )
            )
        return version_periods_by_employee

    def _get_calendar_periods(self, start, stop, check_contract=True):
        return self.sudo()._get_version_periods(
            start, stop, "resource_calendar_id", check_contract
        )

    @api.model
    def _get_all_versions_with_contract_overlap_with_period(self, date_from, date_to):
        all_employees = self.search(
            ["|", ("active", "=", True), ("active", "=", False)]
        )
        return all_employees._get_versions_with_contract_overlap_with_period(
            date_from, date_to
        )

    def _get_unusual_days(self, date_from, date_to=None):
        if self:
            self.check_singleton()
        date_from_date = datetime.strptime(date_from, "%Y-%m-%d %H:%M:%S").date()
        date_to_date = (
            datetime.strptime(date_to, "%Y-%m-%d %H:%M:%S").date()
            if date_to
            else date_from_date
        )
        if not self:
            _debug.logic(
                "unusual_days_calendar",
                reason="no_employee",
                company=self.env.company.id,
                calendar=self.env.company.resource_calendar_id.id,
            )
            return self.env.company.resource_calendar_id._get_unusual_days(
                datetime.combine(date_from_date, time.min, tzinfo=UTC),
                datetime.combine(date_to_date, time.max, tzinfo=UTC),
                self.env.company,
            )
        employee_versions = (
            self.env["hr.version"]
            .sudo()
            .search([("employee_id", "=", self.id)])
            .filtered(lambda v: v._has_contract_overlap(date_from_date, date_to_date))
        )
        if not employee_versions:
            _debug.logic(
                "unusual_days_calendar",
                reason="no_contract_version",
                employee=self.id,
                start=date_from_date,
                stop=date_to_date,
                calendar=self.resource_calendar_id.id,
            )
            return self.resource_calendar_id._get_unusual_days(
                datetime.combine(date_from_date, time.min).replace(tzinfo=UTC),
                datetime.combine(date_to_date, time.max).replace(tzinfo=UTC),
                self.company_id,
            )
        _debug.logic(
            "unusual_days_versions",
            employee=self.id,
            start=date_from_date,
            stop=date_to_date,
            versions=employee_versions,
        )
        unusual_days = {}
        for version in employee_versions:
            tmp_date_from = max(date_from_date, version.date_start)
            tmp_date_to = (
                min(date_to_date, version.date_end)
                if version.date_end
                else date_to_date
            )
            unusual_days.update(
                version.resource_calendar_id.sudo(False)._get_unusual_days(
                    datetime.combine(
                        fields.Date.from_string(tmp_date_from), time.min
                    ).replace(tzinfo=UTC),
                    datetime.combine(
                        fields.Date.from_string(tmp_date_to), time.max
                    ).replace(tzinfo=UTC),
                    self.company_id,
                )
            )
        return unusual_days

    def _get_employee_field_names_to_empty_on_archive(self) -> list:
        return ["parent_id", "coach_id"]

    def _get_user_field_names_to_empty_on_archive(self):
        return []

    def _get_employee_tz(self):
        self.check_singleton()
        return timezone(self.tz) if self.tz else None

    def _get_version_windows(self, start, stop, tz=None):
        self.check_singleton()
        versions = self.sudo()._get_versions_with_contract_overlap_with_period(
            start.date(), stop.date()
        )
        for version in versions:
            window_start = self._combine_tz(version.date_start, time.min, tz)
            window_stop = (
                self._combine_tz(version.date_end + timedelta(days=1), time.min, tz)
                if version.date_end
                else stop
            )
            yield (
                version,
                max(start, window_start),
                min(stop, window_stop),
                version.resource_calendar_id,
            )

    def _get_fields_store_avatar_card(self, target):
        employee_fields = [
            "company_id",
            Store.One("department_id", ["name"]),
            "work_email",
            Store.One("work_location_id", ["location_type", "name"]),
            Store.Attr("work_phone", lambda e: e.phone_ids._primary().number),
        ]
        user = target.get_user(self.env)
        if user.has_group("hr.group_hr_user"):
            employee_fields.append("job_title")
        if len(self) > 0:
            names = [
                field.field_name if isinstance(field, Store.Attr) else field
                for field in employee_fields
            ]
            self.fetch([name for name in names if name in self._fields] + ["phone_ids"])
        return employee_fields

    def get_bank_account_salary_allocation(self, account_id) -> tuple:
        allocation = self.salary_allocation_ids.filtered(
            lambda a: a.bank_account_id.id == account_id
        )[:1]
        if not allocation:
            return 0, True
        return allocation.amount, allocation.amount_is_percentage

    def get_remaining_percentage(self):
        self.check_singleton()
        allocated = sum(
            self.salary_allocation_ids.filtered("amount_is_percentage").mapped("amount")
        )
        return max(0.0, 100.0 - allocated)

    def _get_accounts_with_fixed_allocations(self):
        self.check_singleton()
        return self.salary_allocation_ids.filtered(
            lambda a: not a.amount_is_percentage
        ).mapped("bank_account_id")

    def _fold_version_windows(self, start, stop, fallback, per_window, combine):
        self.check_singleton()
        employee_tz = self._get_employee_tz()
        windows = list(self._get_version_windows(start, stop, employee_tz))
        if not windows:
            _debug.logic(
                "version_windows",
                employee=self.id,
                windows=0,
                start=start,
                stop=stop,
                fallback_calendar=self.resource_calendar_id.id,
            )
            return fallback(self.resource_calendar_id, employee_tz)
        _debug.logic(
            "version_windows",
            employee=self.id,
            windows=len(windows),
            start=start,
            stop=stop,
        )
        result = None
        for index, window in enumerate(windows):
            part = per_window(index, window, employee_tz)
            result = part if result is None else combine(result, part)
        return result

    def _get_attendance_intervals(self, start, stop, lunch=False):
        self.check_singleton()
        if not lunch:
            return self._get_expected_attendances(start, stop)
        resource = self.resource_id

        def fallback(calendar, _tz):
            return calendar._attendance_intervals_batch(
                start, stop, resource, lunch=True
            )[resource.id]

        def per_window(_index, window, _tz):
            _version, window_start, window_stop, calendar = window
            return calendar._attendance_intervals_batch(
                window_start, window_stop, resources=resource, lunch=True
            )[resource.id]

        return self._fold_version_windows(
            start, stop, fallback, per_window, lambda a, b: a | b
        )

    def _get_expected_attendances(self, date_from, date_to):
        self.check_singleton()
        resource = self.resource_id
        company_domain = [("company_id", "in", [False, self.company_id.id])]

        def fallback(calendar, tz):
            return calendar._work_intervals_batch(
                date_from,
                date_to,
                tz=tz,
                resources=resource,
                compute_leaves=True,
                domain=company_domain,
            )[resource.id]

        def per_window(index, window, tz):
            version, window_start, window_stop, calendar = window
            if index == 0:
                window_start = max(
                    date_from,
                    self._combine_tz(version.contract_date_start, time.min, tz),
                )
            return calendar._work_intervals_batch(
                window_start,
                window_stop,
                tz=tz,
                resources=resource,
                compute_leaves=True,
                domain=[*company_domain, ("time_type_id.is_work", "=", False)],
            )[resource.id]

        return self._fold_version_windows(
            date_from, date_to, fallback, per_window, lambda a, b: a | b
        )

    def _get_calendar_attendances(self, date_from, date_to):
        self.check_singleton()

        def fallback(calendar, tz):
            return calendar.get_work_duration_data(
                date_from,
                date_to,
                domain=[("company_id", "in", [False, self.company_id.id])],
                tz=tz,
            )

        def per_window(_index, window, tz):
            version, window_start, window_stop, calendar = window
            return calendar.get_work_duration_data(
                window_start,
                window_stop,
                domain=[("company_id", "in", [False, version.company_id.id])],
                tz=tz,
            )

        def combine(total, part):
            return {
                "days": total["days"] + part["days"],
                "hours": total["hours"] + part["hours"],
            }

        return self._fold_version_windows(
            date_from, date_to, fallback, per_window, combine
        )

    @api.model
    def get_import_templates(self):
        return [
            {
                "label": self.env._("Import Template for Employees"),
                "template": "/hr/static/xls/hr_employee.xls",
            }
        ]

    def _get_age(self, target_date=None):
        self.check_singleton()
        if target_date is None:
            target_date = fields.Date.context_today(self.env.user)
        return relativedelta(target_date, self.birthday).years if self.birthday else 0

    def _dispose_departed_resources(self) -> None:
        today = fields.Date.context_today(self)
        departed = self.filtered(
            lambda employee: (
                employee.departure_date
                and employee.departure_date <= today
                and employee.resource_id.state != "disposed"
            )
        )
        for departure, employees in departed.grouped("departure_date").items():
            employees.resource_id._transition("disposed", date=departure)

    @api.model
    def _cron_dispose_departed_resources(self) -> None:
        self.with_context(active_test=False).search(
            [
                ("departure_date", "<=", fields.Date.context_today(self)),
                ("resource_id.state", "!=", "disposed"),
            ]
        )._dispose_departed_resources()

    def _get_departure_date(self):
        self.check_singleton()
        if self.date_end and self.date_end < fields.Date.today():
            return self.departure_date
        return False

    def _get_versions_with_contract_overlap_with_period(self, date_from, date_to):
        return self.version_ids.filtered_domain(
            [
                ("contract_date_start", "!=", False),
                ("contract_date_start", "<=", date_to),
                "|",
                ("contract_date_end", ">=", date_from),
                ("contract_date_end", "=", False),
            ]
        )

    def get_avatar_card_data(self, field_names):
        stored = [fname for fname in field_names if fname != "work_phone"]
        data = self.read(stored)
        if "work_phone" in field_names:
            for employee, values in zip(self, data, strict=True):
                values["work_phone"] = employee.phone_ids._primary().number
        return data

    def _update_missing_avatars(self) -> None:
        if not self.env["ir.ui.view"].sudo(False).has_access("write"):
            _debug.logic(
                "missing_avatars_skipped", employees=self, reason="no_view_write_access"
            )
            return
        for partner in self.partner_id:
            if partner.image_1920 or not (partner.name or "").strip():
                continue
            _debug.pipeline("avatar_generated", partner=partner.id)
            partner.image_1920 = partner._prepare_avatar_svg()

    def _sync_user(self, user):
        vals = {"user_id": user.id}
        if user:
            vals["partner_id"] = user.partner_id.id
        return vals

    def _bind_resource_to_party(self) -> None:
        for employee in self:
            if employee.resource_id.partner_id != employee.partner_id:
                _debug.pipeline(
                    "resource_party_synced",
                    employee=employee.id,
                    resource=employee.resource_id.id,
                    old_partner=employee.resource_id.partner_id.id,
                    new_partner=employee.partner_id.id,
                )
                employee.resource_id.partner_id = employee.partner_id

    def _update_party_vals(self, company_id, vals_list) -> None:
        unbound = [
            vals
            for vals in vals_list
            if not vals.get("resource_id") and not vals.get("partner_id")
        ]
        parties = (
            self.env["res.partner"]
            .sudo()
            .create(
                [
                    {"name": vals.get("name"), "tz": vals.get("tz") or False}
                    for vals in unbound
                ]
            )
        )
        for vals, party in zip(unbound, parties, strict=True):
            vals["partner_id"] = party.id
        pending = [vals for vals in vals_list if not vals.get("resource_id")]
        resource_by_party = {
            resource.partner_id.id: resource
            for resource in self.env["res.partner"]
            .browse([vals["partner_id"] for vals in pending])
            ._get_resources(self.env["res.company"].browse(company_id))
        }
        for vals in pending:
            if resource := resource_by_party.get(vals["partner_id"]):
                _debug.pipeline(
                    "existing_resource_taken",
                    partner=vals["partner_id"],
                    resource=resource.id,
                )
                vals["resource_id"] = resource.id

    def _prepare_resource_values(self, vals, tz):
        resource_vals = super()._prepare_resource_values(vals, tz)
        resource_vals["partner_id"] = vals.get("partner_id")
        user_id = vals.pop("user_id", None)
        if user_id:
            resource_vals["user_id"] = user_id
        active_status = vals.get("active")
        if active_status is not None:
            resource_vals["active"] = active_status
        return resource_vals

    _IDENTIFIER_TYPES = {
        "identification_id": "NATIONAL_ID",
        "ssnid": "SSN",
        "passport_id": "PASSPORT",
        "barcode": "BADGE",
    }
    _IDENTIFIER_EXPIRY = {
        "PASSPORT": "passport_expiration_date",
    }

    @api.depends(
        "partner_id.identifier_ids.type_id",
        "partner_id.identifier_ids.value",
        "partner_id.identifier_ids.valid_until",
    )
    def _compute_identifiers(self) -> None:
        for employee in self:
            by_code = {
                identifier.type_id.code: identifier
                for identifier in employee.partner_id.identifier_ids
            }
            for fname, code in self._IDENTIFIER_TYPES.items():
                employee[fname] = by_code[code].value if code in by_code else False
            for code, fname in self._IDENTIFIER_EXPIRY.items():
                row = by_code.get(code)
                employee[fname] = row.valid_until if row else False

    def _inverse_identifiers(self) -> None:
        Type = self.env["res.partner.identifier.type"].sudo()
        types = {
            identifier_type.code: identifier_type
            for identifier_type in Type.search(
                [("code", "in", list(self._IDENTIFIER_TYPES.values()))]
            )
        }
        for employee in self:
            partner = employee.partner_id.sudo()
            by_code = {
                identifier.type_id.code: identifier
                for identifier in partner.identifier_ids
            }
            for fname, code in self._IDENTIFIER_TYPES.items():
                value = employee[fname]
                row = by_code.get(code)
                vals = {"value": value}
                expiry = self._IDENTIFIER_EXPIRY.get(code)
                if expiry:
                    vals["valid_until"] = employee[expiry]
                if not value:
                    if expiry and employee[expiry]:
                        raise ValidationError(
                            self.env._(
                                "%(expiry_label)s cannot be set without "
                                "%(number_label)s: an expiry date belongs to a "
                                "document, and there is no document to attach "
                                "it to.",
                                expiry_label=self._fields[expiry].string,
                                number_label=self._fields[fname].string,
                            )
                        )
                    if row:
                        _debug.lifecycle(
                            "identifier_cleared",
                            employee=employee.id,
                            code=code,
                            row=row.id,
                        )
                        row.unlink()
                    continue
                if row:
                    changed = {k: v for k, v in vals.items() if row[k] != v}
                    if changed:
                        _debug.lifecycle(
                            "identifier_changed",
                            employee=employee.id,
                            code=code,
                            row=row.id,
                            keys=sorted(changed),
                        )
                        row.write(changed)
                else:
                    _debug.lifecycle(
                        "identifier_created",
                        employee=employee.id,
                        code=code,
                        partner=partner.id,
                    )
                    partner.identifier_ids.create(
                        {"partner_id": partner.id, "type_id": types[code].id, **vals}
                    )

    @api.model
    def _search_identifier(self, code, operator, value):
        absent = _searches_for_absence(operator, value)
        if absent is not None:
            return [
                (
                    "partner_id.identifier_ids",
                    "not any" if absent else "any",
                    [("type_id.code", "=", code)],
                )
            ]
        return [
            (
                "partner_id.identifier_ids",
                "any",
                [("type_id.code", "=", code), ("value", operator, value)],
            )
        ]

    def _search_identification_id(self, operator, value):
        return self._search_identifier("NATIONAL_ID", operator, value)

    def _search_ssnid(self, operator, value):
        return self._search_identifier("SSN", operator, value)

    def _search_passport_id(self, operator, value):
        return self._search_identifier("PASSPORT", operator, value)

    def _search_barcode(self, operator, value):
        return self._search_identifier("BADGE", operator, value)

    def _search_passport_expiration_date(self, operator, value) -> list:
        absent = _searches_for_absence(operator, value)
        if absent is not None:
            dated = [("type_id.code", "=", "PASSPORT"), ("valid_until", "!=", False)]
            has = "not any" if absent else "any"
            return [("partner_id.identifier_ids", has, dated)]
        return [
            (
                "partner_id.identifier_ids",
                "any",
                [("type_id.code", "=", "PASSPORT"), ("valid_until", operator, value)],
            )
        ]

    def _reparent_private_address(self) -> None:
        employees = self.sudo()
        other_residents = dict(
            employees.with_context(active_test=False)._read_group(
                [
                    ("private_address_id", "in", employees.private_address_id.ids),
                    ("id", "not in", employees.ids),
                ],
                ["private_address_id"],
                ["__count"],
            )
        )
        for employee in employees:
            home = employee.private_address_id
            contact = employee.partner_id
            if (
                home
                and contact
                and home.parent_id != contact
                and home not in other_residents
            ):
                _debug.pipeline(
                    "home_reparented",
                    employee=employee.id,
                    home=home.id,
                    old_parent=home.parent_id.id,
                    new_parent=contact.id,
                )
                home.parent_id = contact

    def _move_identifiers_to_party(self, former_parties) -> None:
        codes = set(self._IDENTIFIER_TYPES.values())
        for employee in self:
            former = former_parties.get(employee)
            party = employee.partner_id
            if not former or not party or former == party:
                continue
            held = {
                identifier.type_id.code for identifier in party.sudo().identifier_ids
            }
            wanted = codes - held
            to_move = former.sudo().identifier_ids.filtered_domain(
                [("type_id.code", "in", list(wanted))]
            )
            if to_move:
                _debug.pipeline(
                    "identifiers_moved",
                    employee=employee.id,
                    identifiers=to_move,
                    former=former.id,
                    party=party.id,
                    held=sorted(held),
                )
                to_move.partner_id = party.id

    def _check_access(self, operation):
        if (
            operation == "read"
            and self.env.context.get("_allow_read_hr_employee")
            is _ALLOW_READ_HR_EMPLOYEE
        ):
            return None
        return super()._check_access(operation)

    @api.depends_context("uid")
    @api.depends("parent_id")
    def _compute_is_manager(self) -> None:
        user_employee = self.env.user.employee_id
        if not user_employee:
            self.is_manager = False
            return
        all_reports = set(
            self.env["hr.employee"]
            .sudo()
            .search([("id", "child_of", user_employee.id)])
            .ids
        )
        for employee in self:
            employee.is_manager = employee.id in all_reports

    @api.depends_context("uid")
    def _compute_is_user(self) -> None:
        user_employee_id = self.env.user.employee_id.id
        for employee in self:
            employee.is_user = employee.id == user_employee_id

    def _retire_former_party(self, former_parties) -> None:
        for employee in self:
            former = former_parties.get(employee)
            party = employee.partner_id
            if not former or not party or former == party:
                continue
            former = former.sudo()
            if (
                former.user_ids
                or former.employee_ids
                or former.is_company
                or former.parent_id
                or former.child_ids
            ):
                _debug.logic(
                    "former_party_kept",
                    employee=employee.id,
                    former=former.id,
                    reason="still_referenced",
                )
                continue
            if former.tag_ids:
                party.sudo().tag_ids = [Command.link(tag.id) for tag in former.tag_ids]
            _debug.lifecycle(
                "former_party_archived",
                employee=employee.id,
                former=former.id,
                tags=len(former.tag_ids),
                party=party.id,
            )
            former.active = False

    def _update_bank_account_contact(self, partner_id) -> None:
        accounts_sudo = (
            self.env["res.partner.bank.account"]
            .sudo()
            .browse(self.salary_bank_account_ids.ids)
        )
        to_move = accounts_sudo.filtered(
            lambda account: account.partner_id.id != partner_id
        )
        if not to_move:
            return
        trusted = to_move.filtered("allow_out_payment")
        _debug.pipeline(
            "bank_accounts_moved",
            employees=self,
            accounts=to_move,
            partner=partner_id,
            losing_trust=trusted,
        )
        if trusted:
            trusted.allow_out_payment = False
        if partner_id:
            to_move.partner_id = partner_id

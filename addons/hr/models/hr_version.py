import logging
from collections import defaultdict
from datetime import date

from babel.dates import format_date, get_date_format
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import babel_locale_parse, frozendict, get_lang

_logger = logging.getLogger(__name__)

_debug = DebugLog(__name__)


def format_date_abbr(env, date):
    lang = get_lang(env)
    locale = babel_locale_parse(lang.code)
    date_format = get_date_format("medium", locale=locale).pattern
    return format_date(date, date_format, locale=locale)


def remove_values_from_other_companies(records, vals_list, default) -> None:
    given = set(default or ())
    companies = records.env["res.company"]
    for record, vals in zip(records, vals_list, strict=False):
        if not vals:
            continue
        company = (
            companies.browse(vals["company_id"])
            if vals.get("company_id")
            else record.company_id
        )
        for name, field in record._fields.items():
            if name in given or name not in vals:
                continue
            if field.type != "many2one" or not (
                field.check_company or field.base_field.check_company
            ):
                continue
            corecord = record[name]
            if "company_id" not in corecord._fields:
                continue
            corecord_company = corecord.company_id
            if corecord_company and corecord_company != company:
                _debug.logic(
                    "copy_drops_foreign_company",
                    record=record,
                    field=name,
                    value=corecord.id,
                    value_company=corecord_company.id,
                    company=company.id,
                )
                del vals[name]


def _get_sorted_difference(values, excluded):
    return sorted(set(values) - set(excluded))


class HrVersion(models.Model):
    _name = "hr.version"
    _description = "Version"
    _inherit = [
        "mixin.mail.thread",
        "mixin.mail.activity",
    ]
    _mail_post_access = "read"
    _order = "date_version"
    _rec_name = "name"
    _access_anchors = frozendict(
        {
            "employee": "employee_id",
        }
    )

    def _default_address_id(self):
        address = self.env.company.partner_id.address_get(["default"])
        return address["default"] if address else False

    @api.model
    def _get_default_structure_type(self, country_id):
        StructureType = self.env["hr.payroll.structure.type"].sudo()
        return StructureType.search(
            [("country_id", "=", country_id)], limit=1
        ) or StructureType.search([("country_id", "=", False)], limit=1)

    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        store=True,
        readonly=False,
        tracking=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        index=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
    )
    name = fields.Char(tracking=True)
    display_name = fields.Char(compute="_compute_display_name")
    active = fields.Boolean(
        default=True,
        tracking=True,
    )

    date_version = fields.Date(
        default=fields.Date.today,
        required=True,
        tracking=True,
        groups="hr.group_hr_user",
    )
    pending_employee_vals = fields.Json(
        copy=False,
        groups="hr.group_hr_user",
    )
    last_modified_uid = fields.Many2one(
        comodel_name="res.users",
        string="Last Modified by",
        default=lambda self: self.env.uid,
        required=True,
        groups="hr.group_hr_user",
    )
    last_modified_date = fields.Datetime(
        string="Last Modified on",
        default=fields.Datetime.now,
        required=True,
        groups="hr.group_hr_user",
    )

    employee_type = fields.Selection(
        selection=[
            ("employee", "Employee"),
            ("worker", "Worker"),
            ("student", "Student"),
            ("trainee", "Trainee"),
            ("contractor", "Contractor"),
            ("freelance", "Freelancer"),
        ],
        default="employee",
        required=True,
        tracking=True,
        groups="hr.group_hr_user",
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        index=True,
        check_company=True,
        tracking=True,
    )
    member_of_department = fields.Boolean(
        string="Member of department",
        compute="_compute_member_of_department",
        search="_search_member_of_department",
        help="Whether the employee is a member of the active user's department or one of it's child department.",
    )
    job_id = fields.Many2one(
        comodel_name="hr.job",
        index=True,
        check_company=True,
        tracking=True,
    )
    job_title = fields.Char(
        compute="_compute_job_title",
        inverse="_inverse_job_title",
        store=True,
        readonly=False,
        tracking=True,
    )
    is_custom_job_title = fields.Boolean(
        compute="_compute_is_custom_job_title",
        default=False,
        store=True,
        groups="hr.group_hr_user",
    )
    address_id = fields.Many2one(
        comodel_name="res.partner",
        string="Work Address",
        default=lambda self: self._default_address_id(),
        store=True,
        readonly=False,
        check_company=True,
        tracking=True,
    )
    work_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        domain="[('address_id', '=', address_id)]",
        tracking=True,
    )

    departure_reason_id = fields.Many2one(
        comodel_name="hr.departure.reason",
        copy=False,
        ondelete="restrict",
        tracking=True,
        groups="hr.group_hr_user",
    )
    departure_description = fields.Html(
        string="Additional Information",
        copy=False,
        classification="hr.private",
    )
    departure_date = fields.Date(
        copy=False,
        tracking=True,
        classification="hr.private",
    )

    resource_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        string="Working Hours",
        compute="_compute_resource_calendar_id",
        inverse="_inverse_resource_calendar_id",
        store=True,
        readonly=False,
        required=True,
        check_company=True,
        tracking=True,
    )
    tz = fields.Selection(related="employee_id.tz")

    contract_date_start = fields.Date(
        string="Contract Start Date",
        tracking=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    contract_date_end = fields.Date(
        string="Contract End Date",
        tracking=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
        help="End date of the contract (if it's a fixed-term contract).",
    )
    trial_date_end = fields.Date(
        string="End of Trial Period",
        tracking=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
        help="End date of the trial period (if there is one).",
    )
    date_start = fields.Date(
        compute="_compute_dates",
        store=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    date_end = fields.Date(
        compute="_compute_dates",
        store=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    is_current = fields.Boolean(
        compute="_compute_date_state",
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    is_past = fields.Boolean(
        compute="_compute_date_state",
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    is_future = fields.Boolean(
        compute="_compute_date_state",
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    is_in_contract = fields.Boolean(
        compute="_compute_is_in_contract",
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )

    contract_template_id = fields.Many2one(
        comodel_name="hr.version",
        domain="[('company_id', '=', company_id), ('employee_id', '=', False)]",
        tracking=True,
        groups="hr.group_hr_user",
        help="Select a contract template to auto-fill the contract form with predefined values. You can still edit the fields as needed after applying the template.",
    )
    structure_type_id = fields.Many2one(
        comodel_name="hr.payroll.structure.type",
        string="Salary Structure Type",
        compute="_compute_structure_type_id",
        store=True,
        readonly=False,
        tracking=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    active_employee = fields.Boolean(
        related="employee_id.active",
        string="Active Employee",
        groups="hr.group_hr_user",
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Currency",
        readonly=True,
    )
    wage = fields.Monetary(
        aggregator="avg",
        tracking=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
        help="Employee's monthly gross wage.",
    )
    contract_wage = fields.Monetary(
        compute="_compute_contract_wage",
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    company_country_id = fields.Many2one(
        comodel_name="res.country",
        related="company_id.country_id",
        string="Company country",
        readonly=True,
    )
    country_code = fields.Char(
        related="company_country_id.code",
        depends=["company_country_id"],
        readonly=True,
    )
    contract_type_id = fields.Many2one(
        comodel_name="hr.contract.type",
        tracking=True,
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )
    additional_note = fields.Text(
        tracking=True,
        classification="hr.private",
    )

    def _domain_hr_responsible_id(self) -> str:
        return (
            "[('share', '=', False), ('company_ids', 'in', company_id), ('all_group_ids', 'in', %s)]"
            % self.env.ref("hr.group_hr_user").id
        )

    hr_responsible_id = fields.Many2one(
        comodel_name="res.users",
        string="HR Responsible",
        default=lambda self: self.env.user,
        required=True,
        domain=_domain_hr_responsible_id,
        tracking=True,
        groups="hr.group_hr_user",
        help="Person responsible for validating the employee's contracts.",
    )

    _check_contract_start_date_defined = models.Constraint(
        "CHECK(contract_date_end IS NULL OR contract_date_start IS NOT NULL)",
        "The contract must have a start date.",
    )

    # In the database rather than in an `@api.constrains`: `wage` is written
    # from the form, from an import and from `get_values_from_contract_template`,
    # and only a CHECK covers all three. NULL passes it, which is what the
    # employee-less contract templates need.
    _check_wage_not_negative = models.Constraint(
        "CHECK(wage >= 0)",
        "The wage cannot be negative.",
    )

    _check_unique_date_version = models.UniqueIndex(
        "(employee_id, date_version) WHERE active = TRUE AND employee_id IS NOT NULL",
        "An employee cannot have multiple active versions sharing the same effective date.",
    )

    @api.depends("employee_id.company_id")
    def _compute_company_id(self):
        for version in self:
            version.company_id = (
                version.employee_id.company_id or version.company_id or self.env.company
            )

    @api.depends("job_id.name")
    def _compute_job_title(self) -> None:
        for version in self:
            if not version.job_id:
                if not version.is_custom_job_title:
                    version.job_title = False
                continue
            if (
                version._origin.job_id != version.job_id
                or not version.is_custom_job_title
            ):
                _debug.logic(
                    "job_title_follows_job",
                    version=version.id,
                    job=version.job_id.id,
                    old_title=version.job_title,
                    new_title=version.job_id.name,
                )
                version.job_title = version.job_id.name

    def _inverse_job_title(self) -> None:
        for version in self:
            version.is_custom_job_title = version.job_title != version.job_id.name

    @api.depends("job_id")
    def _compute_is_custom_job_title(self) -> None:
        for version in self:
            if version._origin.job_id != version.job_id:
                version.is_custom_job_title = False

    @staticmethod
    def _has_period_overlap(start_a, end_a, start_b, end_b) -> bool:
        end_a = end_a or date.max
        end_b = end_b or date.max
        return start_a <= end_b and start_b <= end_a

    @staticmethod
    def _is_day_in_period(start, end, day) -> bool:
        return bool(HrVersion._has_period_overlap(start, end, day, day))

    def _is_unsettled(self, fname) -> bool:
        field = self._fields[fname]
        return bool(
            self.env.is_to_compute(field, self) or self.env.is_protected(field, self)
        )

    def _is_version_in_force(self) -> bool:
        return self.employee_id.version_id == self

    @api.constrains("resource_calendar_id", "company_id")
    def _check_resource_calendar_company(self) -> None:
        for version in self:
            if version._is_unsettled("resource_calendar_id"):
                continue
            if not version._is_version_in_force():
                continue
            calendar_company = version.resource_calendar_id.company_id
            if (
                calendar_company
                and version.company_id
                and calendar_company != version.company_id
            ):
                raise ValidationError(
                    self.env._(
                        "The working hours %(calendar)s belong to %(calendar_company)s "
                        "and cannot be used by %(employee)s of %(company)s.",
                        calendar=version.resource_calendar_id.display_name,
                        calendar_company=calendar_company.display_name,
                        employee=version.display_name,
                        company=version.company_id.display_name,
                    )
                )

    @api.constrains("department_id", "company_id")
    def _check_department_company(self) -> None:
        for version in self:
            if version._is_unsettled("department_id"):
                continue
            if not version._is_version_in_force():
                continue
            department_company = version.department_id.company_id
            if (
                department_company
                and version.company_id
                and department_company != version.company_id
            ):
                raise ValidationError(
                    self.env._(
                        "The department %(department)s belongs to "
                        "%(department_company)s and cannot hold %(employee)s of "
                        "%(company)s.",
                        department=version.department_id.display_name,
                        department_company=department_company.display_name,
                        # NOT version.display_name -- a version is named by its
                        # date, which reads as nonsense in this sentence.
                        employee=version.employee_id.display_name
                        or version.display_name,
                        company=version.company_id.display_name,
                    )
                )

    @_debug.perf.timed
    @api.constrains("employee_id", "contract_date_start", "contract_date_end")
    def _check_dates(self) -> None:
        version_read_group = (
            self.env["hr.version"]
            .sudo()
            ._read_group(
                [
                    ("id", "not in", self.ids),
                    ("employee_id", "in", self.employee_id.ids),
                    ("contract_date_start", "!=", False),
                ],
                ["employee_id", "contract_date_start:day", "contract_date_end:day"],
                ["id:recordset"],
            )
        )
        dates_per_employee = defaultdict(list)
        for employee, date_start, date_end, versions in version_read_group:
            dates_per_employee[employee].append((date_start, date_end, versions))
        for version in self.sudo():
            if not version.contract_date_start or not version.employee_id:
                continue
            if (
                version.contract_date_end
                and version.contract_date_start > version.contract_date_end
            ):
                raise ValidationError(
                    self.env._(
                        "Start date (%(start)s) must be earlier than contract end date (%(end)s).",
                        start=version.contract_date_start,
                        end=version.contract_date_end,
                    )
                )
            if not version.active:
                continue
            contract_date_end = version.contract_date_end or date.max
            contract_period_exists = False
            for date_start, date_end, _versions in dates_per_employee[
                version.employee_id
            ]:
                date_to = date_end or date.max
                if (
                    date_start == version.contract_date_start
                    and date_to == contract_date_end
                ):
                    contract_period_exists = True
                    continue
                if self._has_period_overlap(
                    date_start,
                    date_end,
                    version.contract_date_start,
                    version.contract_date_end,
                ):
                    raise ValidationError(
                        self.env._(
                            "%s already has a contract running during the selected period.\n\n"
                            "Please either:\n\n"
                            "- Change the start date so that it doesn't overlap with the existing contract, or\n"
                            "- Create a new employee if this employee should have multiple active contracts.",
                            version.employee_id.display_name,
                        )
                    )
            _debug.logic(
                "contract_period",
                version=version.id,
                start=version.contract_date_start,
                stop=version.contract_date_end,
                employee=version.employee_id.id,
                period="existing" if contract_period_exists else "new",
            )
            if not contract_period_exists:
                dates_per_employee[version.employee_id].append(
                    (version.contract_date_start, version.contract_date_end, version)
                )

    def check_contract_finished(self) -> None:
        if self.contract_date_start and not self.contract_date_end:
            raise ValidationError(
                self.env._(
                    "Before creating a new contract, close the current one by setting an end date."
                )
            )

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({k for vals in vals_list for k in vals}),
            )
        Version = self.env["hr.version"]
        for vals in vals_list:
            if "contract_template_id" in vals:
                contract_vals = Version._prepare_vals_from_contract_template(
                    Version.browse(vals["contract_template_id"])
                )
                if _debug.logic.enabled:
                    _debug.logic(
                        "template_supplies",
                        template=vals["contract_template_id"],
                        keys=_get_sorted_difference(contract_vals, vals),
                    )
                vals.update({**contract_vals, **vals})
            if "resource_calendar_id" not in vals:
                vals["resource_calendar_id"] = self._get_default_calendar(vals).id
        vals_list = [self._normalize_calendar_vals(vals) for vals in vals_list]
        versions = super().create(vals_list)
        _debug.lifecycle("created", versions=versions)
        return versions

    @api.model
    def _get_default_calendar(self, vals):
        if vals.get("company_id"):
            company = self.env["res.company"].browse(vals["company_id"])
        elif vals.get("employee_id"):
            company = self.env["hr.employee"].browse(vals["employee_id"]).company_id
        else:
            company = self.env.company
        return self.env["resource.calendar"]._get_company_calendar(company)

    @api.model
    def _normalize_calendar_vals(self, vals):
        return self.env["resource.calendar"]._normalize_calendar_vals(
            vals, "resource_calendar_id"
        )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_last_version(self) -> None:
        for employee_id, versions in self.grouped("employee_id").items():
            if employee_id.version_ids == versions:
                raise ValidationError(
                    self.env._(
                        "Employee %s must always have at least one active version."
                    )
                    % employee_id.name
                )

    def _check_employee_keeps_a_version(self, vals) -> None:
        if "employee_id" in vals and self.filtered(
            lambda v: (
                v.employee_id
                and v.employee_id.version_ids <= self
                and vals["employee_id"] != v.employee_id.id
            )
        ):
            raise ValidationError(
                self.env._("Cannot unassign all the active versions of an employee.")
            )
        if (
            "active" in vals
            and not vals["active"]
            and self.filtered(
                lambda v: v.employee_id and v.employee_id.version_ids <= self
            )
        ):
            raise ValidationError(
                self.env._("Cannot archive all the active versions of an employee.")
            )

    def _check_one_contract_per_write(self) -> None:
        for versions_by_employee in self.grouped("employee_id").values():
            if len(versions_by_employee.grouped("contract_date_start").keys()) > 1:
                raise ValidationError(
                    self.env._(
                        "Cannot modify multiple versions contract dates with different contracts at once."
                    )
                )

    def _get_contract_dates_to_sync(self, vals, first_version):
        dates_vals = {}
        for fname in ("contract_date_start", "contract_date_end"):
            dates_vals[fname] = (
                fields.Date.to_date(vals.get(fname))
                if fname in vals
                else first_version[fname]
            )
        return dates_vals

    @api.depends("company_id")
    def _compute_resource_calendar_id(self) -> None:
        for version in self:
            calendar = version.resource_calendar_id
            if not calendar or (
                calendar.company_id and calendar.company_id != version.company_id
            ):
                _debug.logic(
                    "calendar_company_default",
                    version=version.id,
                    calendar=calendar.id,
                    company=version.company_id.id,
                    default_calendar=version.company_id.resource_calendar_id.id,
                )
                version.resource_calendar_id = self._get_default_calendar(
                    {"company_id": version.company_id.id}
                )

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        remove_values_from_other_companies(self, vals_list, default)
        return vals_list

    @_debug.perf.timed
    def write(self, vals):
        _debug.lifecycle(
            "write",
            versions=self,
            keys=sorted(vals),
            sync_contract_dates=bool(self.env.context.get("sync_contract_dates")),
        )
        self._check_employee_keeps_a_version(vals)
        vals = self._normalize_calendar_vals(vals)

        if self.env.context.get("sync_contract_dates") or (
            "contract_date_start" not in vals and "contract_date_end" not in vals
        ):
            return super().write(vals)

        self._check_one_contract_per_write()

        multiple_versions = self
        if vals.get("contract_date_start"):
            unique_versions = multiple_versions.filtered(
                lambda v: len(v.employee_id.version_ids) == 1
            )
            multiple_versions -= unique_versions
            if unique_versions:
                _debug.logic(
                    "date_version_follows_contract",
                    versions=unique_versions,
                    contract_start=vals["contract_date_start"],
                )
                unique_versions.with_context(sync_contract_dates=True).write(
                    {**vals, "date_version": vals["contract_date_start"]}
                )

        if not any(multiple_versions.mapped("contract_date_start")):
            _debug.logic(
                "plain_write", versions=multiple_versions, reason="no_contract"
            )
            return super(HrVersion, multiple_versions).write(vals)

        new_vals = {
            f_name: f_value
            for f_name, f_value in vals.items()
            if (f_name != "contract_date_start" or not f_value)
            and f_name != "contract_date_end"
        }
        for employee, versions in multiple_versions.grouped("employee_id").items():
            first_version = next(iter(versions), versions)
            dates_vals = self._get_contract_dates_to_sync(vals, first_version)
            if not first_version.contract_date_start:
                _debug.pipeline(
                    "contract_dates_taken",
                    employee=employee.id,
                    versions=versions,
                    dates=dates_vals,
                )
                versions.with_context(sync_contract_dates=True).write(dates_vals)
                continue
            versions_to_sync = employee._get_contract_versions(
                date_start=first_version.contract_date_start,
                date_end=first_version.contract_date_end,
            )
            all_versions_to_sync = self.env["hr.version"]
            for contract_versions in versions_to_sync.values():
                all_versions_to_sync |= contract_versions.get(
                    first_version.contract_date_start, self.env["hr.version"]
                )
            _debug.pipeline(
                "contract_dates_synced",
                employee=employee.id,
                contract_start=first_version.contract_date_start,
                dates=dates_vals,
                versions=all_versions_to_sync,
            )
            if all_versions_to_sync:
                all_versions_to_sync.with_context(sync_contract_dates=True).write(
                    dates_vals
                )

        _debug.logic(
            "remaining_write", keys=sorted(new_vals), versions=multiple_versions
        )
        return super(HrVersion, multiple_versions).write(new_vals)

    def get_formview_action(self, access_uid=None):
        res = super().get_formview_action(access_uid=access_uid)
        context = res.get("context", {})
        if self.employee_id:
            res["res_model"] = "hr.employee"
            res["res_id"] = self.employee_id.id
            res["context"] = dict(context, version_id=self.id)
            _debug.logic(
                "form_redirected_to_employee",
                version=self.id,
                employee=self.employee_id.id,
            )
        elif not context.get("form_view_ref", False):
            res["context"] = dict(
                context, form_view_ref="hr.hr_contract_template_form_view"
            )
            _debug.logic("opens_as_contract_template", version=self.id)
        return res

    @api.depends_context("lang")
    @api.depends("date_version", "name", "employee_id")
    def _compute_display_name(self):
        for version in self:
            version.display_name = (
                version.name
                if not version.employee_id
                else format_date_abbr(version.env, version.date_version)
            )

    @api.depends("date_start", "date_end")
    def _compute_date_state(self) -> None:
        today = fields.Date.today()
        for version in self:
            version.is_current = version.date_start <= today and (
                not version.date_end or version.date_end >= today
            )
            version.is_past = bool(version.date_end and version.date_end < today)
            version.is_future = version.date_start > today

    @api.depends("date_start", "date_end", "contract_date_start")
    def _compute_is_in_contract(self) -> None:
        for version in self:
            version.is_in_contract = version._is_in_contract()

    def _is_in_contract(self, date=None) -> bool:
        date = date or fields.Date.today()
        if not self.contract_date_start:
            return False
        return self.date_start <= date and (not self.date_end or self.date_end >= date)

    def _has_contract_overlap(self, date_from, date_to) -> bool:
        if not self.contract_date_start:
            return False
        return bool(
            self._has_period_overlap(
                self.date_start, self.date_end, date_from or date.min, date_to
            )
        )

    @api.model
    def _get_whitelist_fields_from_template(self):
        return [
            "job_id",
            "department_id",
            "contract_type_id",
            "structure_type_id",
            "wage",
            "resource_calendar_id",
            "hr_responsible_id",
        ]

    def _prepare_vals_from_contract_template(self, contract_template):
        if not contract_template:
            return {}
        company = contract_template.company_id or self.env.company
        whitelist = self.with_company(company)._get_whitelist_fields_from_template()
        contract_template_vals = contract_template.sudo().copy_data()[0]
        HrVersion = self.env["hr.version"]
        vals = {
            field: value
            for field, value in contract_template_vals.items()
            if field in whitelist
            and not HrVersion._fields[field].related
            and HrVersion._has_field_access(HrVersion._fields[field], "read")
        }
        _debug.logic(
            "contract_template_vals",
            template=contract_template.id,
            company=company.id,
            keys=sorted(vals),
            whitelist=whitelist,
        )
        return vals

    @api.depends("wage")
    def _compute_contract_wage(self) -> None:
        for version in self:
            version.contract_wage = version._get_contract_wage()

    def _get_contract_wage(self):
        if not self:
            return 0
        self.check_singleton()
        return self[self._get_contract_wage_field_name()]

    def _get_contract_wage_field_name(self):
        self.check_singleton()
        return "wage"

    def _get_normalized_wage(self):
        wage = self._get_contract_wage()
        if self.resource_calendar_id:
            if not self.resource_calendar_id.hours_per_week:
                return 0
            return wage * 12 / 52 / self.resource_calendar_id.hours_per_week
        return wage

    @api.depends_context("uid", "company")
    @api.depends("department_id")
    def _compute_member_of_department(self) -> None:
        user_employee = self.env["hr.employee"]._get_valid_employee_for_user()
        active_department = user_employee.department_id
        _debug.logic(
            "member_of_department",
            versions=self,
            user_employee=user_employee.id,
            department=active_department.id,
        )
        if not active_department:
            self.member_of_department = False
        else:
            child_departments = self.env["hr.department"].search(
                [("id", "child_of", active_department.ids)]
            )
            for version in self:
                version.member_of_department = (
                    version.department_id in child_departments
                )

    def _search_member_of_department(self, operator, value):
        return self.env["hr.employee"]._search_member_of_department_domain(operator)

    @api.depends("company_id", "company_id.country_id")
    def _compute_structure_type_id(self) -> None:
        default_structure_by_country = {}
        for version in self:
            if not version.structure_type_id or (
                version.structure_type_id.country_id
                and version.structure_type_id.country_id
                != version.company_id.country_id
            ):
                country_id = version.company_id.country_id.id
                if country_id not in default_structure_by_country:
                    default_structure_by_country[country_id] = (
                        self._get_default_structure_type(country_id)
                    )
                _debug.logic(
                    "structure_type_defaulted",
                    version=version.id,
                    structure_type=version.structure_type_id.id,
                    default=default_structure_by_country[country_id].id,
                    country=country_id,
                )
                version.structure_type_id = default_structure_by_country[country_id]

    @api.depends(
        "contract_date_start",
        "contract_date_end",
        "date_version",
        "employee_id",
        "employee_id.version_ids.date_version",
    )
    @_debug.perf.timed
    def _compute_dates(self) -> None:
        sibling_versions = self.env["hr.version"].search(
            [("employee_id", "in", self.employee_id.ids)],
            order="date_version",
        )
        date_versions_by_employee = defaultdict(list)
        for sibling in sibling_versions:
            date_versions_by_employee[sibling.employee_id].append(sibling.date_version)

        for version in self:
            version.date_start = (
                max(version.date_version, version.contract_date_start)
                if version.contract_date_start
                else version.date_version
            )

            next_date_version = next(
                (
                    date_version
                    for date_version in date_versions_by_employee[version.employee_id]
                    if date_version > version.date_version
                ),
                False,
            )
            date_version_end = (
                next_date_version + relativedelta(days=-1)
                if next_date_version
                else False
            )

            if date_version_end and version.contract_date_end:
                version.date_end = min(date_version_end, version.contract_date_end)
            elif date_version_end:
                version.date_end = date_version_end
            else:
                version.date_end = version.contract_date_end
            _debug.logic(
                "dates_computed",
                version=version.id,
                start=version.date_start,
                stop=version.date_end,
                date_version=version.date_version,
                next_date_version=next_date_version,
                contract_start=version.contract_date_start,
                contract_end=version.contract_date_end,
            )

    def _inverse_resource_calendar_id(self) -> None:
        for employee, versions in self.grouped("employee_id").items():
            current_version = employee.current_version_id
            for version in versions:
                if (
                    version == current_version
                    and employee.resource_id.calendar_id != version.resource_calendar_id
                ):
                    _debug.pipeline(
                        "current_version_calendar",
                        version=version.id,
                        employee=employee.id,
                        resource=employee.resource_id.id,
                        from_calendar=employee.resource_id.calendar_id.id,
                        to_calendar=version.resource_calendar_id.id,
                    )
                    employee.resource_id.calendar_id = version.resource_calendar_id

    def _get_salary_costs_factor(self):
        self.check_singleton()
        return 12.0

    def _is_struct_from_country(self, country_code) -> bool:
        self.check_singleton()
        self_sudo = self.sudo()
        return bool(
            self_sudo.structure_type_id
            and self_sudo.structure_type_id.country_id.code == country_code
        )

    def _get_schedule_tz(self):
        self.check_singleton()
        return (
            self.tz
            or self.resource_calendar_id.tz
            or self.company_id.resource_calendar_id.tz
            or "UTC"
        )

    def action_view_version(self):
        self.check_singleton()

        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.employee",
            "res_id": self.employee_id.id,
            "views": [[False, "form"]],
            "target": "current",
            "context": {
                "version_id": self.id,
            },
        }

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Self

from odoo import api, fields, models
from odoo.exceptions import RedirectWarning, ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

_logger = logging.getLogger(__name__)


class HrVersion(models.Model):
    _inherit = "hr.version"
    _description = "Employee Contract"

    schedule_pay = fields.Selection(
        selection=lambda self: self.env[
            "hr.payroll.structure.type"
        ]._get_selection_schedule_pay(),
        string="Pay Schedule",
        compute="_compute_schedule_pay",
        store=True,
        readonly=False,
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    show_schedule_pay = fields.Boolean(
        compute="_compute_show_schedule_pay",
        groups="hr.group_hr_user",
    )
    resource_calendar_id = fields.Many2one(
        help="""Employee's working schedule.
        When left empty, the employee is considered to have a fully flexible schedule, allowing them to work without any time limit, anytime of the week.
        """
    )
    contract_date_start = fields.Date(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    contract_date_end = fields.Date(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    trial_date_end = fields.Date(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    date_start = fields.Date(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    date_end = fields.Date(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    wage = fields.Monetary(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    contract_wage = fields.Monetary(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    work_entry_source = fields.Selection(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    is_current = fields.Boolean(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    is_past = fields.Boolean(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    is_future = fields.Boolean(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    is_in_contract = fields.Boolean(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    structure_type_id = fields.Many2one(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    contract_type_id = fields.Many2one(
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )

    hours_per_week = fields.Float(
        related="resource_calendar_id.hours_per_week",
        groups="hr.group_hr_user",
    )
    full_time_required_hours = fields.Float(
        related="resource_calendar_id.full_time_required_hours",
        groups="hr.group_hr_user",
    )
    is_fulltime = fields.Boolean(
        related="resource_calendar_id.is_fulltime",
        groups="hr.group_hr_user",
    )
    wage_type = fields.Selection(
        selection=[("monthly", "Fixed Wage"), ("hourly", "Hourly Wage")],
        compute="_compute_wage_type",
        store=True,
        readonly=False,
        tracking=True,
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    hourly_wage = fields.Monetary(
        tracking=True,
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
        help="Employee's hourly gross wage.",
    )

    _check_hourly_wage_positive = models.Constraint(
        "CHECK(hourly_wage >= 0)",
        "The hourly wage must be a positive value.",
    )
    payslips_count = fields.Integer(
        string="# Payslips",
        compute="_compute_payslips_count",
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )
    work_time_rate = fields.Float(
        string="Work time rate",
        compute="_compute_work_time_rate",
        store=True,
        readonly=True,
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
        help="Work time rate versus full time working schedule.",
    )
    standard_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        compute="_compute_standard_calendar_id",
        store=True,
        readonly=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
        groups="hr.group_hr_user",
    )
    is_non_resident = fields.Boolean(
        string="Non-resident",
        tracking=True,
        groups="hr.group_hr_user",
        help="If the employee is not a legal resident of the country where they are employed",
    )
    disabled = fields.Boolean(
        tracking=True,
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
        help="If the employee is declared disabled by law",
    )

    structure_id = fields.Many2one(
        related="structure_type_id.default_struct_id",
        groups="hr.group_hr_user",
    )
    payroll_properties = fields.Properties(
        definition="structure_id.version_properties_definition",
        precompute=False,
        copy=True,
        readonly=False,
        classification="hr.compensation",
        groups="hr_payroll.group_hr_payroll_user",
    )

    @api.constrains("contract_date_start", "contract_date_end", "departure_reason_id")
    def _check_contract_dates_cover_validated_payslips(self) -> None:
        """A validated payslip is a paid one: its period cannot fall outside
        the contract it was computed from. Regular payslips are already
        protected from this by their validated work entries, which
        hr_work_entry refuses to delete, but an off-cycle payslip -- a bonus,
        a settlement -- validates without validating any work entry, so
        nothing else stands in the way there.

        A version with a departure reason is left out: closing the contract is
        the point of registering a departure, and wizard.hr.employee.register.departure writes
        the reason before it writes the end date.
        """
        conflicts = []
        for version in self.filtered(
            lambda v: v.contract_date_start and not v.departure_reason_id
        ):
            outside = Domain("date_from", "<", version.contract_date_start)
            if version.contract_date_end:
                outside |= Domain("date_to", ">", version.contract_date_end)
            conflicts.append(Domain("version_id", "=", version.id) & outside)
        if not conflicts:
            return

        payslips = self.env["hr.payslip"].search(
            Domain("state", "in", ["validated", "paid"])
            & Domain("is_refunded", "=", False)
            & Domain("is_refund_payslip", "=", False)
            & Domain.OR(conflicts)
        )
        if not payslips:
            return

        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_payroll.action_view_hr_payslip_month_form"
        )
        action["domain"] = [("id", "in", payslips.ids)]
        raise RedirectWarning(
            self.env._(
                "These contract dates would leave out payslips that are already "
                "validated and not refunded. Refund them first, or register a "
                "departure if the employee is leaving."
            ),
            action,
            self.env._("View Payslips to Refund"),
        )

    @api.depends("structure_type_id")
    def _compute_schedule_pay(self) -> None:
        for version in self:
            if version.structure_type_id:
                # default_schedule_pay is optional on the type: a cleared
                # selection must not blank the version's schedule.
                version.schedule_pay = (
                    version.structure_type_id.default_schedule_pay or "monthly"
                )
            elif not version.schedule_pay:
                version.schedule_pay = "monthly"

    @api.depends("structure_type_id")
    def _compute_wage_type(self) -> None:
        for version in self:
            version.wage_type = version.structure_type_id.wage_type

    @api.depends(
        "resource_calendar_id.hours_per_week",
        "company_id.resource_calendar_id.hours_per_week",
    )
    def _compute_work_time_rate(self) -> None:
        for version in self:
            hours_per_week = version.resource_calendar_id.hours_per_week
            hours_per_week_ref = version.company_id.resource_calendar_id.hours_per_week
            if not hours_per_week and not hours_per_week_ref:
                version.work_time_rate = 1
            else:
                version.work_time_rate = hours_per_week / (
                    hours_per_week_ref or hours_per_week
                )

    @api.depends("company_id")
    def _compute_standard_calendar_id(self) -> None:
        for version in self:
            if not version.standard_calendar_id:
                version.standard_calendar_id = version.company_id.resource_calendar_id

    def _compute_show_schedule_pay(self) -> None:
        number_of_possibilities = len(
            self.env["hr.payroll.structure.type"]._get_selection_schedule_pay()
        )
        for version in self:
            version.show_schedule_pay = number_of_possibilities > 1

    def _compute_payslips_count(self) -> None:
        count_data = self.env["hr.payslip"]._read_group(
            [("version_id", "in", self.ids)], ["version_id"], ["__count"]
        )
        mapped_counts = {version.id: count for version, count in count_data}
        for version in self:
            version.payslips_count = mapped_counts.get(version.id, 0)

    def _get_property_input_value(self, code):
        self.check_singleton()
        rule = self.env["hr.salary.rule"].search(
            [("code", "=", code), ("struct_id", "=", self.structure_id.id)], limit=1
        )
        if rule:
            return dict(self.payroll_properties).get(str(rule.id), 0.00)
        return 0.0

    def _set_property_input_value(self, code, value) -> None:
        self.check_singleton()
        current_properties = dict(self.payroll_properties)
        rule = self.env["hr.salary.rule"].search(
            [("code", "=", code), ("struct_id", "=", self.structure_id.id)], limit=1
        )
        if rule:
            rule_name = str(rule.id)
            if rule_name in current_properties:
                current_properties.update({rule_name: value})
                self.write({"payroll_properties": current_properties})
            else:
                _logger.warning(
                    "Dropped salary-configurator value for rule %s (code %s):"
                    " not a known property on structure %s",
                    rule.id,
                    code,
                    self.structure_id.id,
                )

    def _get_salary_costs_factor(self):
        self.check_singleton()
        factors = {
            "annually": 1,
            "semi-annually": 2,
            "quarterly": 4,
            "bi-monthly": 6,
            "monthly": 12,
            "semi-monthly": 24,
            "bi-weekly": 26,
            "weekly": 52,
            "daily": 52
            * (
                self.resource_calendar_id._get_days_per_week()
                if self.resource_calendar_id
                else 5
            ),
        }
        return factors.get(self.schedule_pay, super()._get_salary_costs_factor())

    def _is_same_occupation(self, version) -> bool:
        self.check_singleton()
        contract_type = self.contract_type_id
        work_time_rate = self.resource_calendar_id.work_time_rate
        return (
            contract_type == version.contract_type_id
            and work_time_rate == version.resource_calendar_id.work_time_rate
        )

    def _get_occupation_dates(self, include_future_contracts=False):
        # Takes several versions and returns all the versions under the same occupation (i.e. the same
        # work rate + the date_from and date_to)
        # include_future_contracts will use versions where the version_date_start is posterior
        # compared to today's date
        result = []
        done_versions = self.env["hr.version"]
        date_today = fields.Date.today()

        def remove_gap(version, other_versions, before=False):
            # We do not consider a gap of more than 4 days to be a same occupation
            # other_versions is considered to be ordered correctly in function of `before`
            current_date = version.date_start if before else version.date_end
            for i, other_version in enumerate(other_versions):
                if not current_date:
                    return other_versions[0:i]
                if before:
                    gap = (current_date - other_version.date_end).days
                    current_date = other_version.date_start
                else:
                    gap = (other_version.date_start - current_date).days
                    current_date = other_version.date_end
                if gap >= 4:
                    return other_versions[0:i]
            return other_versions

        for version in self:
            if version in done_versions:
                continue
            versions = version  # hr.version(38,)
            date_from = version.date_start
            date_to = version.date_end
            all_versions = (
                (version.employee_id.version_ids - version)
                .filtered(
                    lambda c: c.date_start <= date_today or include_future_contracts
                )
                .sorted("date_start", reverse=True)
            )  # hr.version(29, 37, 38, 39, 41) -> hr.version(29, 37, 39, 41)
            before_versions = all_versions.filtered_domain(
                [("date_start", "<", version.date_start)]
            )
            before_versions = remove_gap(version, before_versions, before=True)
            after_versions = all_versions.filtered_domain(
                [("date_start", ">", version.date_start)]
            ).sorted(key="date_start")
            after_versions = remove_gap(version, after_versions)

            for before_version in before_versions:
                if version._is_same_occupation(before_version):
                    date_from = before_version.date_start
                    versions |= before_version
                else:
                    break

            for after_version in after_versions:
                if version._is_same_occupation(after_version):
                    date_to = after_version.date_end
                    versions |= after_version
                else:
                    break
            result.append((versions, date_from, date_to))
            done_versions |= versions
        return result

    def _get_normalized_wage(self):
        wage = self._get_contract_wage()
        if self.wage_type == "hourly" or not self.resource_calendar_id.hours_per_week:
            return wage
        else:
            return (
                wage
                * self._get_salary_costs_factor()
                / 52
                / self.resource_calendar_id.hours_per_week
            )

    def _get_contract_wage_field_name(self):
        self.check_singleton()
        if self.wage_type == "hourly":
            return "hourly_wage"
        return super()._get_contract_wage_field_name()

    def action_view_payslips(self):
        # [XBO] TODO: to remove if we don't want to display the button in the list view of version
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_payroll.action_view_hr_payslip_month_form"
        )
        action.update({"domain": [("version_id", "=", self.id)]})
        return action

    def _get_domain_work_hours(self, date_from, date_to, domain=None):
        return Domain.AND(
            [
                domain or Domain.TRUE,
                Domain("state", "in", ["validated", "draft"]),
                Domain("version_id", "in", self.ids),
                Domain("date", ">=", date_from),
                Domain("date", "<=", date_to),
            ]
        )

    def _preprocess_work_hours_data(self, work_data, date_from, date_to) -> None:
        """
        Method is meant to be overriden, see hr_payroll_attendance
        """
        return

    def get_work_hours(self, date_from, date_to, domain=None):
        # Get work hours between 2 dates (datetime.date), grouped per company
        # so _get_work_hours can look up each company's calendar/timezone.
        assert not isinstance(date_from, datetime)
        assert not isinstance(date_to, datetime)

        work_data = defaultdict(int)

        versions_by_company = defaultdict(lambda: self.env["hr.version"])
        for version in self:
            versions_by_company[version.company_id] += version

        # We don't need the timezone immediately here, but we need the uniqueness
        # of the key so that we can guarantee one timezone per set of versions.
        _debug.perf.count(
            "work_hours_by_company",
            versions=self,
            companies=len(versions_by_company),
        )
        for company, versions in versions_by_company.items():
            work_data_tz = (
                versions.with_company(company)
                .sudo()
                ._get_work_hours(date_from, date_to, domain=domain)
            )
            for work_entry_type_id, hours in work_data_tz.items():
                work_data[work_entry_type_id] += hours
        return work_data

    def _get_work_hours(self, date_from, date_to, domain=None):
        """
        Returns the amount (expressed in hours) of work
        for a version between two dates.
        If called on multiple versions, sum work amounts of each version.

        :param date_from: The start date
        :param date_to: The end date
        :returns: a dictionary {work_entry_id: hours_1, work_entry_2: hours_2}
        """
        assert not isinstance(date_from, datetime)
        assert not isinstance(date_to, datetime)

        work_entries = self.env["hr.work.entry"]._read_group(
            self._get_domain_work_hours(date_from, date_to, domain=domain),
            ["work_entry_type_id"],
            ["duration:sum"],
        )
        work_data = defaultdict(int)
        work_data.update(
            {
                work_entry_type.id: duration_sum
                for work_entry_type, duration_sum in work_entries
            }
        )
        self._preprocess_work_hours_data(work_data, date_from, date_to)
        return work_data

    def _get_default_work_entry_type_id(self):
        return (
            self.structure_type_id.default_work_entry_type_id.id
            or super()._get_default_work_entry_type_id()
        )

    def _get_fields_that_recompute_payslip(self):
        return list({version._get_contract_wage_field_name() for version in self})

    def _get_nearly_expired_contracts(self, outdated_days, company_id=False):
        today = fields.Date.today()
        nearly_expired_versions = self.search(
            [
                ("company_id", "=", company_id or self.env.company.id),
                ("contract_date_end", ">=", today),
                ("contract_date_end", "<", outdated_days),
            ]
        )

        # Check if no new contracts starting after the end of the expiring one
        nearly_expired_versions_without_new_versions = self.env["hr.version"]
        new_versions_grouped_by_employee = {
            employee.id
            for [employee] in self._read_group(
                [
                    ("company_id", "=", company_id or self.env.company.id),
                    ("contract_date_start", ">=", outdated_days),
                    ("employee_id", "in", nearly_expired_versions.employee_id.ids),
                ],
                groupby=["employee_id"],
            )
        }

        for expired_version in nearly_expired_versions:
            if expired_version.employee_id.id not in new_versions_grouped_by_employee:
                nearly_expired_versions_without_new_versions |= expired_version
        return nearly_expired_versions_without_new_versions

    @api.model
    def _get_whitelist_fields_from_template(self):
        return super()._get_whitelist_fields_from_template() + ["payroll_properties"]

    def _payslipped_versions(self) -> Self:
        """The versions a validated or paid payslip was computed from."""
        payslips = (
            self.env["hr.payslip"]
            .sudo()
            .search(
                [("version_id", "in", self.ids), ("state", "in", ["validated", "paid"])]
            )
        )
        return self.browse(payslips.version_id.ids)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_payslipped(self) -> None:
        if pinned := self._payslipped_versions():
            raise ValidationError(
                self.env._(
                    "These employee records have validated payslips and cannot be "
                    "deleted:\n%(records)s",
                    records="\n".join(f" - {v.display_name}" for v in pinned),
                )
            )

    def write(self, vals):
        _debug.lifecycle("write", versions=self, fields=list(vals))
        if (
            "active" in vals
            and not vals["active"]
            and (pinned := self._payslipped_versions())
        ):
            raise ValidationError(
                self.env._(
                    "These employee records have validated payslips and cannot be "
                    "archived:\n%(records)s",
                    records="\n".join(f" - {v.display_name}" for v in pinned),
                )
            )
        if self and not self.env.context.get("tracking_disable"):
            # Force to track wage in employee form if any changes is found after version write
            self.employee_id._track_prepare(
                {version.sudo()._get_contract_wage_field_name() for version in self}
            )
        res = super().write(vals)
        # sudo like the _track_prepare lookup above: the field-name resolution
        # reads wage_type, which is payroll-groups-gated, and the writer only
        # needs hr.version write rights.
        dependendant_fields = self.sudo()._get_fields_that_recompute_payslip()
        if any(key in dependendant_fields for key in vals):
            _debug.pipeline(
                "payslip_recompute_triggered",
                versions=self,
                fields=sorted(set(vals) & set(dependendant_fields)),
            )
            for version_sudo in self.sudo():
                version_sudo._recompute_payslips(
                    version_sudo.date_start, version_sudo.date_end or date.max
                )
        return res

    def copy(self, default=None):
        # todo: Remove this override once properties properly work with copy
        new_version = super().copy(default)
        if new_version.sudo().structure_id == self.sudo().structure_id:
            new_version.write({"payroll_properties": dict(self.payroll_properties)})
        return new_version

    def _recompute_work_entries(self, date_from, date_to) -> None:
        self.check_singleton()
        super()._recompute_work_entries(date_from, date_to)
        self._recompute_payslips(date_from, date_to)

    def _recompute_payslips(self, date_from, date_to) -> None:
        self.check_singleton()
        all_payslips = (
            self.env["hr.payslip"]
            .sudo()
            .search(
                [
                    ("version_id", "=", self.id),
                    ("state", "=", "draft"),
                    ("date_from", "<=", date_to),
                    ("date_to", ">=", date_from),
                    ("company_id", "=", self.company_id.id),
                ]
            )
            .filtered(lambda p: p.is_regular)
        )
        _debug.logic(
            "payslips_to_recompute",
            version=self,
            payslips=all_payslips,
            date_from=str(date_from),
            date_to=str(date_to),
        )
        if all_payslips:
            all_payslips.action_refresh_from_work_entries()

    def action_new_salary_attachment(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Salary Adjustment"),
            "res_model": "hr.salary.attachment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_employee_ids": self.employee_id.ids},
        }

    def action_configure_template_inputs(self):
        self.check_singleton()
        action = self.structure_id.action_get_structure_inputs()
        action["domain"].append(("input_usage_employee", "=", True))
        return action

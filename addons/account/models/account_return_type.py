import datetime
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import date_utils
from odoo.tools.misc import format_date

_debug = DebugLog(__name__)

PERIODS = [
    ("monthly", "Monthly"),
    ("2_months", "Every 2 months"),
    ("trimester", "Quarterly"),
    ("4_months", "Every 4 months"),
    ("semester", "Semi-annually"),
    ("year", "Annually"),
    ("fiscalyear", "Fiscal Year"),
]

MONTHS_PER_PERIOD = {
    "year": 12,
    "semester": 6,
    "4_months": 4,
    "trimester": 3,
    "2_months": 2,
    "monthly": 1,
}


class AccountReturnType(models.Model):
    _name = "account.return.type"
    _inherit = ["mixin.mail.thread"]
    _description = "Accounting Return Type"

    name = fields.Char(
        translate=True,
        required=True,
        tracking=True,
    )
    category = fields.Selection(
        selection=[
            ("account_return", "Tax Return"),
            ("audit", "Audit"),
        ],
        string="Type",
        default="account_return",
        required=True,
        tracking=True,
    )
    report_id = fields.Many2one(
        comodel_name="report.formula",
        index="btree",
        tracking=True,
    )
    is_tax_return_type = fields.Boolean(
        string="Is a Tax Return Return Type",
        compute="_compute_report_return_type",
    )
    is_ec_sales_list_return_type = fields.Boolean(
        string="Is an EC Sales List Return Type",
        compute="_compute_report_return_type",
    )

    auto_generate = fields.Boolean(
        string="Auto Generated",
        compute="_compute_auto_generate",
        store=True,
        copy=False,
        readonly=False,
    )
    country_id = fields.Many2one(
        comodel_name="res.country",
        compute="_compute_country_id",
        store=True,
        readonly=False,
        tracking=True,
    )
    payment_bank_account_id = fields.Many2one(
        comodel_name="res.partner.bank.account",
        tracking=True,
    )
    payment_partner_id = fields.Many2one(
        comodel_name="res.partner",
        compute="_compute_payment_partner_id",
        store=True,
        readonly=False,
        tracking=True,
        help="The authority the tax is owed to. It is the partner of the closing entry's "
        "settlement line and of the payments that settle it.",
    )
    settle_per_concept = fields.Boolean(
        string="Settle Each Tax on Its Account",
        tracking=True,
        help="The tax closing leaves each tax group's amount due on that group's payable "
        "account, with the authority as partner, and the return is paid once those "
        "lines are reconciled with money that left the bank. For an authority paid "
        "once for several taxes whose accounts must stay apart.",
    )
    is_informative = fields.Boolean(
        string="Informative",
        tracking=True,
        help="The return files information and owes no tax: even on a tax report it posts "
        "no tax closing, sets no tax lock date and has nothing to pay.",
    )
    filing_channel = fields.Selection(
        selection="_selection_filing_channel",
        tracking=True,
        help="How a return of this type reaches the authority. Empty, submitting only "
        "records that it was submitted.",
    )
    settlement_account_id = fields.Many2one(
        comodel_name="account.account",
        company_dependent=True,
        domain="[('account_type', '=', 'liability_payable'), ('reconcile', '=', True)]",
        tracking=True,
        help="When set, the tax closing moves the net amount due of every tax group into one "
        "line on this account, and the return is paid once that line is reconciled with "
        "money that left the bank.",
    )
    states_workflow = fields.Selection(
        selection=[
            ("generic_state_review", "Review"),
            ("generic_state_review_submit", "Review, Submit"),
            ("generic_state_tax_report", "Review, Submit, Pay"),
            ("generic_state_only_pay", "Pay"),
        ],
        string="States",
        compute="_compute_states_workflow",
        store=True,
        readonly=False,
        help="Determines the workflow of the return.",
    )

    deadline_periodicity = fields.Selection(
        selection=PERIODS,
        string="Periodicity",
        company_dependent=True,
        tracking=True,
    )
    default_deadline_periodicity = fields.Selection(
        selection=PERIODS,
        string="Default Periodicity",
    )
    deadline_start_date = fields.Date(
        string="Start Date",
        company_dependent=True,
        tracking=True,
        help="Used to compute covered period based on the selected periodicity.",
    )
    default_deadline_start_date = fields.Date(string="Default Start Date")
    deadline_days_delay = fields.Integer(
        string="Deadline",
        company_dependent=True,
        tracking=True,
        help="By default, Odoo applies its own deadline for returns (shown as 0). Entering a value here will override it and be used as the new deadline.",
    )
    default_deadline_days_delay = fields.Integer(string="Default Deadline")
    is_master_data = fields.Boolean(compute="_compute_is_master_data")

    @api.model_create_multi
    @_debug.perf.timed
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                model=self._name,
                count=len(vals_list),
                fields=sorted({key for vals in vals_list for key in vals}),
            )
        return_types = super().create(vals_list)

        all_companies = self.env["res.company"].sudo().search([])
        return_types.sudo()._set_default_values(all_companies)

        return return_types

    def _set_default_values(self, companies) -> None:
        for company in companies:
            for return_type in self.with_company(company):
                return_type.deadline_periodicity = (
                    return_type.deadline_periodicity
                    or return_type.default_deadline_periodicity
                )
                return_type.deadline_start_date = (
                    return_type.deadline_start_date
                    or return_type.default_deadline_start_date
                )
                return_type.deadline_days_delay = (
                    return_type.deadline_days_delay
                    or return_type.default_deadline_days_delay
                )

    @api.depends("report_id", "is_informative")
    def _compute_report_return_type(self) -> None:
        tax_report = self.env.ref("account.generic_tax_report")
        generic_ec_sales_report = self.env.ref("account.generic_ec_sales_report")
        for record in self:
            report = record.report_id
            record.is_tax_return_type = (
                report
                and not record.is_informative
                and tax_report in (report, report.root_report_id)
            )
            record.is_ec_sales_list_return_type = (
                report and generic_ec_sales_report in (report, report.root_report_id)
            )

    @api.model
    def _selection_filing_channel(self) -> list:
        return self.env["account.return.submission"]._fields["channel"].selection

    @api.depends("payment_bank_account_id")
    def _compute_payment_partner_id(self) -> None:
        for return_type in self:
            return_type.payment_partner_id = (
                return_type.payment_bank_account_id.partner_id
                or return_type.payment_partner_id
            )

    @api.depends("report_id.country_id")
    def _compute_country_id(self) -> None:
        for return_type in self:
            return_type.country_id = (
                return_type.report_id.country_id
                if not return_type.country_id and return_type.report_id.country_id
                else return_type.country_id
            )

    @api.constrains("country_id")
    def _check_report_country(self) -> None:
        for return_type in self:
            if (
                return_type.report_id.country_id
                and return_type.report_id.country_id != return_type.country_id
            ):
                raise ValidationError(
                    self.env._(
                        "The return type country must be the same as the report country"
                    )
                )

    @api.depends("category")
    def _compute_auto_generate(self) -> None:
        for return_type in self:
            return_type.auto_generate = return_type.category == "account_return"

    @api.depends("report_id", "category", "is_informative")
    def _compute_states_workflow(self) -> None:
        for return_type in self:
            if return_type.is_ec_sales_list_return_type:
                return_type.states_workflow = "generic_state_review_submit"
            elif return_type.category == "audit":
                return_type.states_workflow = "generic_state_review"
            elif return_type.is_tax_return_type:
                return_type.states_workflow = "generic_state_tax_report"
            else:
                return_type.states_workflow = "generic_state_review"

    def _compute_is_master_data(self) -> None:
        xml_id = self.get_external_id()
        for record in self:
            record.is_master_data = bool(xml_id.get(record.id))

    @_debug.perf.timed
    def copy_data(self, default=None):
        _debug.lifecycle("copy_data", records=self)
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        if "name" not in default:
            for return_type, vals in zip(self, vals_list, strict=False):
                vals["name"] = self.env._("%s (copy)", return_type.name)
        return vals_list

    def copy_translations(self, new, excluded=()) -> None:
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

    def _can_return_exist(self, company, tax_unit=False) -> bool:
        is_foreign_vat = (
            self.report_id
            and company.tax_config_id.account_fiscal_country_id.code
            != self.report_id.country_id.code
        )

        is_tax_unit_main_comp = not tax_unit or tax_unit.main_company_id == company

        all_branch_companies_with_same_vat = company._get_branches_with_same_vat()
        sorted_branch_companies_with_same_vat = sorted(
            all_branch_companies_with_same_vat,
            key=lambda comp: len(comp._get_ancestor_ids(include_self=True)),
        )
        is_main_branch = (
            not company.parent_id or company == sorted_branch_companies_with_same_vat[0]
        )

        return is_foreign_vat or (is_tax_unit_main_comp and is_main_branch)

    @api.model
    @_debug.perf.timed
    def _cron_sync_all_returns(self) -> None:
        _debug.lifecycle("_cron_sync_all_returns", records=self)
        now = fields.Datetime.now()
        date_upper_bound = now - relativedelta(days=1)
        root_companies = (
            self.env["res.company"]
            .sudo()
            .search(
                [
                    ("parent_id", "=", False),
                    ("account_config_id.account_opening_date", "!=", False),
                    "|",
                    ("account_config_id.account_last_return_cron_refresh", "=", False),
                    (
                        "account_config_id.account_last_return_cron_refresh",
                        "<",
                        date_upper_bound,
                    ),
                ],
                limit=2,
            )
        )

        _debug.logic(
            "cron_companies_selected",
            companies=root_companies,
            retrigger=len(root_companies) > 1,
        )
        if root_companies:
            to_treat = root_companies[0]
            self._sync_all_returns(to_treat)
            to_treat.account_config_id.account_last_return_cron_refresh = now

            if len(root_companies) > 1:
                self.env["ir.cron"]._trigger_ref(
                    "account.ir_cron_generate_account_return"
                )

            else:
                self._send_submission_reminder()

    @api.model
    def _send_submission_reminder(self) -> None:
        if not (
            mail_template := self.env.ref(
                "account.email_template_tax_return_deadline",
                raise_if_not_found=False,
            )
        ):
            return

        returns_to_submit = (
            self.env["account.return"]
            .search(
                [
                    ("state", "not in", ("submitted", "paid")),
                    ("date_deadline", "=", fields.Date.today() + relativedelta(days=7)),
                ]
            )
            .filtered("is_tax_return")
        )
        for account_return in returns_to_submit:
            for user in self.env.ref(
                "account.group_account_manager"
            ).user_ids.filtered_domain(
                [("company_ids", "in", account_return.company_ids.ids)]
            ):
                mail_template.with_context(partner=user.partner_id).send_mail(
                    account_return.id
                )

    @api.model
    @_debug.perf.timed
    def _sync_all_returns(self, root_companies) -> None:
        root_companies = root_companies.filtered(
            lambda x: x.account_config_id.account_opening_date
        )
        if not root_companies:
            _debug.logic("_sync_all_returns_no_root_company_opening")
            return
        _debug.pipeline("_sync_all_returns", root_companies=root_companies)

        all_tax_units_root_domain = [("company_ids", "child_of", root_companies.ids)]
        all_tax_units = (
            self.env["account.tax.unit"].sudo().search([*all_tax_units_root_domain])
        )

        all_domestic_tax_units = self.env["account.tax.unit"]
        for company in root_companies:
            fiscal_country = company.tax_config_id.account_fiscal_country_id
            domestic_tax_unit = all_tax_units.filtered_domain(
                [
                    ("country_id", "=", fiscal_country.id),
                    ("company_ids", "in", company.ids),
                ]
            )
            self._generate_all_returns(fiscal_country.code, company, domestic_tax_unit)
            all_domestic_tax_units += domestic_tax_unit

        for tax_unit in all_tax_units - all_domestic_tax_units:
            self._generate_all_returns(
                tax_unit.country_id.code, tax_unit.main_company_id, tax_unit
            )

        fpos_root_company_domain = [("company_id", "child_of", root_companies.ids)]
        all_foreign_vat_fpos = (
            self.env["account.fiscal.position"]
            .sudo()
            .search([("foreign_vat", "!=", False), *fpos_root_company_domain])
        )
        for company, fiscal_positions in all_foreign_vat_fpos.grouped(
            lambda x: x.company_id
        ).items():
            for country_code in {fpos.country_id.code for fpos in fiscal_positions}:
                self._generate_all_returns(country_code, company, None)

        return_root_company_domain = [("company_ids", "in", root_companies.ids)]
        all_return_that_might_be_deleted = (
            self.env["account.return"]
            .sudo()
            .search(
                [
                    ("date_lock", "=", False),
                    ("is_completed", "=", False),
                    ("manually_created", "=", False),
                    *return_root_company_domain,
                ]
            )
        )
        returns_to_unlink = self.env["account.return"]
        for return_to_check in all_return_that_might_be_deleted:
            if (
                not return_to_check.type_id._can_return_exist(
                    return_to_check.company_id, return_to_check.tax_unit_id
                )
                or return_to_check.date_deadline
                < return_to_check.company_id.account_config_id.account_opening_date
            ):
                returns_to_unlink |= return_to_check
        _debug.pipeline(
            "_sync_all_returns_vacuum_unlinking",
            all_return_that_might_be_deleted_count=len(
                all_return_that_might_be_deleted
            ),
            returns_to_unlink=returns_to_unlink,
        )
        returns_to_unlink.sudo().unlink()

    @api.model
    @_debug.perf.timed
    def _generate_all_returns(self, country_code, main_company, tax_unit=None):

        if self.env.context.get("only_refresh_conditional_types"):
            return

        if (
            main_company.sudo().tax_config_id.account_fiscal_country_id.code
            == country_code
        ):
            search_domain = Domain.AND(
                [
                    Domain("auto_generate", "=", True),
                    Domain.OR(
                        [
                            Domain("country_id", "=", False),
                            Domain("country_id.code", "=", country_code),
                        ]
                    ),
                ]
            )
        else:
            search_domain = Domain.AND(
                [
                    Domain("country_id.code", "=", country_code),
                    Domain("auto_generate", "=", True),
                ]
            )

        report_types = self.env["account.return.type"].sudo().search(search_domain)
        _debug.pipeline(
            "_generate_all_returns",
            company=main_company,
            country=country_code,
            tax_unit=tax_unit,
            types=report_types,
        )
        for report_type in report_types:
            report_type._try_create_returns_for_fiscal_year(
                main_company, tax_unit=tax_unit
            )

    @api.onchange("category")
    def _onchange_category(self) -> None:
        for return_type in self:
            if return_type.category == "audit":
                return_type.with_company(self.env.company).deadline_periodicity = "year"

    @_debug.perf.timed
    def _try_create_returns_for_fiscal_year(
        self, main_company, tax_unit, allow_duplicates=False, bypass_period_check=False
    ):
        self.check_singleton()
        if self.report_id.filter_multi_company != "tax_units":
            tax_unit = False

        today = datetime.date.today()
        next_year = today + relativedelta(years=1)

        has_forced_dates = self.env.context.get(
            "forced_date_from"
        ) and self.env.context.get("forced_date_to")
        if has_forced_dates:
            date_from = fields.Date.from_string(self.env.context["forced_date_from"])
            date_to = fields.Date.from_string(self.env.context["forced_date_to"])
        else:
            date_from = today - relativedelta(years=1)
            date_to = next_year
        _debug.pipeline(
            "generation_window_resolved",
            returntype=self,
            company=main_company,
            tax_unit=tax_unit,
            date_from=date_from,
            date_to=date_to,
            forced_dates=bool(has_forced_dates),
            allow_duplicates=allow_duplicates,
        )

        if not self._can_return_exist(main_company, tax_unit):
            returns_to_unlink = (
                self.env["account.return"]
                .sudo()
                .search(
                    [
                        ("company_id", "=", main_company.id),
                        ("date_lock", "=", False),
                        ("is_completed", "=", False),
                        ("type_id", "=", self.id),
                        ("date_to", ">=", date_from),
                        ("date_from", "<=", date_to),
                        ("manually_created", "=", False),
                    ]
                )
            )
            _debug.logic(
                "return_cannot_exist",
                returntype=self,
                company=main_company,
                unlinked=returns_to_unlink,
            )
            returns_to_unlink.sudo().unlink()
            return None

        if not tax_unit and not main_company.parent_id and main_company.child_ids:
            other_main_companies = self.env["res.company"]
            to_treat = [(main_company.vat, main_company)]
            while to_treat:
                (vat_from_parent, current_company) = to_treat.pop()

                for child_company in current_company.child_ids:
                    if (
                        child_company.vat
                        and child_company.vat != vat_from_parent
                        and child_company.account_config_id.account_return_periodicity
                        and child_company.account_config_id.account_return_reminder_day
                    ):
                        other_main_companies |= child_company
                    to_treat.append((child_company.vat, child_company))

            _debug.logic(
                "branch_subtrees_with_own_vat",
                returntype=self,
                company=main_company,
                branch_main_companies=other_main_companies,
            )
            for other_main_company in other_main_companies:
                if other_main_company.account_config_id.account_opening_date:
                    self._try_create_returns_for_fiscal_year(
                        other_main_company, tax_unit
                    )

        expected_companies = (
            self.env["account.return"]
            .sudo()
            ._get_company_ids(main_company, tax_unit, self.report_id)
        )
        date_pointer = date_from
        periods = []
        deadline_date = date_pointer
        type_xml_id = self.get_external_id()[self.id]
        if self.env.context.get("force_periodicity_violation"):
            periods.append((date_from, date_to))
        else:
            while date_pointer < date_to and (
                deadline_date <= next_year or bypass_period_check
            ):
                period_date_from, period_date_to = self._get_period_boundaries(
                    main_company, date_pointer
                )
                deadline_date = self.env["account.return"]._evaluate_deadline(
                    main_company, self, type_xml_id, period_date_from, period_date_to
                )
                if (
                    main_company.account_config_id.account_opening_date or date.min
                ) <= deadline_date <= next_year or bypass_period_check:
                    periods.append((period_date_from, period_date_to))
                date_pointer = period_date_to + relativedelta(days=1)
        _debug.pipeline(
            "periods_computed",
            returntype=self,
            company=main_company,
            periods=len(periods),
            last_deadline=deadline_date,
            bypass_period_check=bypass_period_check,
        )

        existing_returns = (
            self.env["account.return"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    (
                        "company_id",
                        "=",
                        main_company.id,
                    ),
                    ("type_id", "=", self.id),
                    ("date_to", ">=", date_from),
                    ("date_from", "<=", date_to),
                ]
            )
        )
        if existing_returns and not allow_duplicates:
            existing_periods = {
                (account_return.date_from, account_return.date_to): self.env[
                    "account.return"
                ].sudo()
                for account_return in existing_returns
            }
            for account_return in existing_returns:
                existing_periods[account_return.date_from, account_return.date_to] |= (
                    account_return
                )
            same_periods = set(periods) & set(existing_periods.keys())

            for same_period in same_periods:
                same_period_returns = existing_periods[same_period]
                for same_period_return in same_period_returns:
                    if (
                        same_period_return.company_id == main_company
                        and not same_period_return.is_completed
                        and not same_period_return.date_lock
                    ):
                        if same_period_return.tax_unit_id != tax_unit:
                            same_period_return.tax_unit_id = tax_unit
                        elif same_period_return.company_ids != expected_companies:
                            same_period_return.company_ids = expected_companies

            periods = list(set(periods) - same_periods)
            periods.sort(key=lambda period: period[0])

            unmatched_existing_periods = set(existing_periods.keys()) - same_periods
            unmatched_existing_periods_posted_returns = self.env["account.return"]
            unmatched_existing_periods_unposted_returns = self.env["account.return"]
            for period in unmatched_existing_periods:
                if (
                    not existing_periods[period].date_lock
                    and not existing_periods[period].is_completed
                ):
                    unmatched_existing_periods_unposted_returns |= existing_periods[
                        period
                    ]
                else:
                    unmatched_existing_periods_posted_returns |= existing_periods[
                        period
                    ]

            unmatched_existing_periods_unposted_returns.filtered(
                lambda r: not r.manually_created
            ).sudo().unlink()

            _debug.logic(
                "existing_periods_reconciled",
                returntype=self,
                company=main_company,
                existing=existing_returns,
                same_periods=len(same_periods),
                unposted=unmatched_existing_periods_unposted_returns,
                posted=unmatched_existing_periods_posted_returns,
                periods_left=len(periods),
            )
            if unmatched_existing_periods_posted_returns:
                most_recent_posted_return = max(
                    unmatched_existing_periods_posted_returns,
                    key=lambda ret: ret.date_to,
                )
                new_periods = [
                    period
                    for period in periods
                    if period[0] > most_recent_posted_return.date_to
                ]
                periods = new_periods
                _debug.logic(
                    "periods_trimmed_after_posted",
                    returntype=self,
                    last_posted=most_recent_posted_return,
                    last_posted_date_to=most_recent_posted_return.date_to,
                    periods_left=len(periods),
                )

        create_vals_list = []
        for period_from, period_to in periods:
            create_vals_list.append(
                {
                    "name": self._get_return_name(main_company, period_from, period_to),
                    "type_id": self.id,
                    "company_id": main_company.id,
                    "date_from": period_from,
                    "date_to": period_to,
                    "tax_unit_id": tax_unit.id if tax_unit else False,
                    "manually_created": bool(self.env.context.get("manually_created")),
                }
            )

        account_returns = self.env["account.return"].sudo().create(create_vals_list)
        _debug.pipeline(
            "returns_created",
            returntype=self,
            company=main_company,
            tax_unit=tax_unit,
            tax_return=account_returns,
        )
        account_returns._update_translated_name()
        return account_returns

    @_debug.perf.timed
    def _try_create_return_for_period(
        self, date_in_period, main_company, tax_unit, allow_duplicates=False
    ) -> None:
        period_start, period_end = self._get_period_boundaries(
            main_company, date_in_period
        )
        existing_return = (
            self.env["account.return"]
            .with_context(active_test=False)
            .search(
                [
                    *self.env["account.return"]._check_company_domain(main_company),
                    ("tax_unit_id", "=", tax_unit.id if tax_unit else None),
                    ("date_from", "=", period_start),
                    ("date_to", "=", period_end),
                    ("type_id", "=", self.id),
                ]
            )
        )

        expected_companies = (
            self.env["account.return"]
            .sudo()
            ._get_company_ids(main_company, tax_unit, self.report_id)
        )
        if existing_return.company_ids != expected_companies:
            _debug.logic(
                "companies",
                tax_return=existing_return,
                company_ids=existing_return.company_ids,
                expected_companies=expected_companies,
            )
            existing_return.company_ids = expected_companies

        if not existing_return or allow_duplicates:
            _debug.lifecycle(
                "creating_return_company",
                returntype=self,
                period_start=period_start,
                period_end=period_end,
                main_company=main_company,
            )
            account_return = self.env["account.return"].create(
                [
                    {
                        "name": self._get_return_name(
                            main_company, period_start, period_end
                        ),
                        "date_from": period_start,
                        "date_to": period_end,
                        "type_id": self.id,
                        "company_id": main_company.id,
                        "tax_unit_id": tax_unit.id if tax_unit else None,
                    }
                ]
            )
            account_return._update_translated_name()

    @_debug.perf.timed
    def _get_return_name(
        self,
        main_company,
        period_from=None,
        period_to=None,
        minimal=False,
        all_lang=False,
    ):
        main_company = main_company.sudo()
        country_code = ""
        if (
            self.report_id
            and self.report_id.country_id
            and main_company.tax_config_id.account_fiscal_country_id
            != self.report_id.country_id
        ):
            if self.report_id and self.report_id.country_id:
                country_code = f"({self.report_id.country_id.code})"
            else:
                country_code = (
                    f"({main_company.tax_config_id.account_fiscal_country_id.code})"
                )
        _debug.logic(
            "return_name_country_suffix",
            returntype=self,
            company=main_company,
            country_code=country_code,
            all_lang=all_lang,
            minimal=minimal,
        )

        if not all_lang:
            return self.env._(
                "%(return_type_name)s %(period_suffix)s %(country_code)s",
                return_type_name=self.name,
                period_suffix=self._get_period_name(
                    main_company,
                    period_from=period_from,
                    period_to=period_to,
                    minimal=minimal,
                ),
                country_code=country_code,
            )
        else:
            return_dict = {}
            installed_langs = self.env["res.lang"].get_installed()
            for lang_code, _lang_name in installed_langs:
                return_dict[lang_code] = self.with_context(lang=lang_code).env._(
                    "%(return_type_name)s %(period_suffix)s %(country_code)s",
                    return_type_name=self.with_context(lang=lang_code).name,
                    period_suffix=self._get_period_name(
                        main_company,
                        period_from=period_from,
                        period_to=period_to,
                        minimal=minimal,
                        lang_code=lang_code,
                    ),
                    country_code=country_code,
                )

            return return_dict

    @api.model
    @_debug.perf.timed
    def _get_period_name(
        self,
        main_company=None,
        period_from=None,
        period_to=None,
        start_day=1,
        start_month=1,
        minimal=False,
        lang_code=None,
    ):
        def infer_periodicity(period_from, period_to):
            def match(dt_from, dt_to):
                return (dt_from, dt_to) == (period_from, period_to)

            if match(
                fields.Date.start_of(period_from, "year"),
                fields.Date.end_of(period_to, "year"),
            ):
                return "year"
            elif match(*date_utils.get_month(period_to)):
                return "monthly"
            elif match(*date_utils.get_quarter(period_to)):
                return "trimester"
            else:
                return "other"

        if not start_day or not start_month:
            if not main_company:
                raise ValidationError(
                    self.env._(
                        "Main company must be provided if start_day and start_month are not provided"
                    )
                )
            start_day, start_month = self._get_start_date_elements(main_company)
            _debug.logic(
                "period_start_from_company",
                company=main_company,
                start_day=start_day,
                start_month=start_month,
            )

        period_suffix = ""
        if period_from and period_to:
            if isinstance(period_from, str):
                period_from = fields.Date.to_date(period_from)

            if isinstance(period_to, str):
                period_to = fields.Date.to_date(period_to)

            if start_day != 1 or start_month != 1:
                period_suffix = f"{format_date(self.env, period_from, lang_code=lang_code)} - {format_date(self.env, period_to, lang_code=lang_code)}"
            else:
                inferred_periodicity = infer_periodicity(period_from, period_to)
                _debug.logic(
                    "periodicity_inferred",
                    period_from=period_from,
                    period_to=period_to,
                    periodicity=inferred_periodicity,
                )
                if inferred_periodicity == "year":
                    period_suffix = f"{period_from.year}"
                elif inferred_periodicity == "trimester":
                    date_format = "qqq yyyy" if not minimal else "qqq"
                    period_suffix = format_date(
                        self.env,
                        period_from,
                        date_format=date_format,
                        lang_code=lang_code,
                    )
                elif inferred_periodicity == "monthly":
                    date_format = "LLLL yyyy" if not minimal else "LLL"
                    period_suffix = format_date(
                        self.env,
                        period_from,
                        date_format=date_format,
                        lang_code=lang_code,
                    )
                elif period_from == fields.Date.start_of(
                    period_from, "month"
                ) and period_to == fields.Date.end_of(period_to, "month"):
                    period_suffix = f"{format_date(self.env, period_from, date_format='LLL yyyy', lang_code=lang_code)} - {format_date(self.env, period_to, date_format='LLL yyyy', lang_code=lang_code)}"
                else:
                    period_suffix = f"{format_date(self.env, period_from, lang_code=lang_code)} - {format_date(self.env, period_to, lang_code=lang_code)}"
        _debug.logic(
            "period_suffix_built",
            aligned_start=start_day == 1 and start_month == 1,
            has_period=bool(period_from and period_to),
            suffix=period_suffix,
            lang=lang_code,
        )
        return period_suffix

    def _get_periodicity(self, company):
        return (
            self.with_company(company).sudo().deadline_periodicity
            or company.sudo().account_config_id.account_return_periodicity
        )

    def _get_start_date(self):
        return self.sudo().deadline_start_date or fields.Date.from_string("2025-01-01")

    def _get_periodicity_months_delay(self, company, date=None):
        periodicity = self._get_periodicity(company)
        if periodicity == "fiscalyear":
            if date:
                fy_dates = company.compute_fiscalyear_dates(date)
                start_date = fy_dates["date_from"]
                end_date = fy_dates["date_to"]
                delta = relativedelta(end_date + relativedelta(days=1), start_date)
                return delta.years * 12 + delta.months

            months = 12
            fiscalyears = self.env["account.fiscal.year"].search(
                [("company_id", "=", company.id)]
            )
            for fiscalyear in fiscalyears:
                delta = relativedelta(
                    fiscalyear.date_to + relativedelta(days=1), fiscalyear.date_from
                )
                fiscal_year_months = delta.years * 12 + delta.months
                months = max(months, fiscal_year_months)
            _debug.logic(
                "fiscalyear_months_fallback",
                company=company,
                fiscalyears=len(fiscalyears),
                months=months,
            )
            return months

        return MONTHS_PER_PERIOD[periodicity]

    def _get_start_date_elements(self, main_company) -> tuple:
        start_date = self.with_company(main_company)._get_start_date()
        return start_date.day, start_date.month

    @_debug.perf.timed
    def _get_period_boundaries(
        self, company_id, date, override_period_months=None, override_start_date=None
    ) -> tuple:
        if self._get_periodicity(company_id) == "fiscalyear":
            fy_dates = company_id.compute_fiscalyear_dates(date)
            _debug.logic(
                "boundaries_from_fiscal_year",
                returntype=self,
                company=company_id,
                date=date,
                date_from=fy_dates.get("date_from"),
                date_to=fy_dates.get("date_to"),
            )
            return fy_dates["date_from"], fy_dates["date_to"]

        period_months = override_period_months or self._get_periodicity_months_delay(
            company_id, date=date
        )

        if override_start_date:
            start_day = override_start_date.day
            start_month = override_start_date.month
        else:
            start_day, start_month = self._get_start_date_elements(company_id)

        aligned_date = date + relativedelta(days=-(start_day - 1))
        year = aligned_date.year
        month_offset = aligned_date.month - start_month
        period_number = (month_offset // period_months) + 1

        if date < datetime.date(date.year, start_month, start_day):
            year -= 1
            period_number = ((12 + month_offset) // period_months) + 1

        month_delta = period_number * period_months

        end_date = datetime.date(year, start_month, 1) + relativedelta(
            months=month_delta, days=start_day - 2
        )
        start_date = datetime.date(year, start_month, 1) + relativedelta(
            months=month_delta - period_months, day=start_day
        )
        _debug.logic(
            "boundaries_computed",
            returntype=self,
            company=company_id,
            date=date,
            period_months=period_months,
            overridden=bool(override_period_months or override_start_date),
            start_day=start_day,
            start_month=start_month,
            period_number=period_number,
            start=start_date,
            end=end_date,
        )

        return start_date, end_date

    @api.depends_context("company")
    @api.depends("name", "report_id")
    @_debug.perf.timed
    def _compute_display_name(self):
        has_foreign_fiscal_pos = bool(
            self.env["account.fiscal.position"].search_count(
                [
                    *self.env["account.fiscal.position"]._check_company_domain(
                        self.env.company.id
                    ),
                    ("foreign_vat", "!=", False),
                ],
                limit=1,
            )
        )
        if not has_foreign_fiscal_pos:
            return super()._compute_display_name()

        for return_type in self:
            if has_foreign_fiscal_pos and return_type.country_id:
                return_type.display_name = (
                    f"{return_type.name} ({return_type.country_id.code})"
                )
            else:
                return_type.display_name = return_type.name
        return None

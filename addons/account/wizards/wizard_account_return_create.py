from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardAccountReturnCreate(models.TransientModel):
    _name = "wizard.account.return.create"
    _description = "Return creation wizard"

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        readonly=True,
        required=True,
    )
    category = fields.Selection(
        selection=[
            ("account_return", "Tax Return"),
            ("audit", "Audit"),
        ],
        default="account_return",
    )
    available_return_type_ids = fields.Many2many(
        comodel_name="account.return.type",
        compute="_compute_available_return_type_ids",
    )
    return_type_id = fields.Many2one(
        comodel_name="account.return.type",
        compute="_compute_return_type_id",
        store=True,
        readonly=False,
        required=True,
        domain="[('id', 'in', available_return_type_ids)]",
    )
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    show_warning_wrong_dates = fields.Boolean(compute="_compute_warnings")
    show_warning_existing_return = fields.Boolean(compute="_compute_warnings")
    show_warning_overlap = fields.Boolean(compute="_compute_warnings")

    regulatory_compliance = fields.Boolean(
        string="Regulatory compliance",
        default=True,
    )
    treasury_financing = fields.Boolean(
        string="Treasury and financing",
        default=True,
    )
    purchases = fields.Boolean(default=True)
    operating_expenses = fields.Boolean(
        string="Operating expenses",
        default=True,
    )
    sales = fields.Boolean(default=True)
    inventory = fields.Boolean(default=True)
    fixed_assets = fields.Boolean(
        string="Fixed assets",
        default=True,
    )
    payroll = fields.Boolean(default=True)
    government = fields.Boolean(default=True)
    equity = fields.Boolean(default=True)
    other = fields.Boolean(
        string="Others",
        default=True,
    )

    is_create_disabled = fields.Boolean(compute="_compute_is_create_disabled")

    @api.depends("available_return_type_ids")
    def _compute_return_type_id(self) -> None:
        for wizard in self:
            if wizard.return_type_id not in wizard.available_return_type_ids:
                _debug.logic(
                    "return_type_defaulted",
                    wizard=wizard,
                    dropped=wizard.return_type_id,
                    available=wizard.available_return_type_ids,
                )
                wizard.return_type_id = wizard.available_return_type_ids[:1]

    @api.depends(
        "show_warning_existing_return",
        "show_warning_overlap",
        "date_from",
        "return_type_id",
        "date_to",
    )
    def _compute_is_create_disabled(self) -> None:
        for wizard in self:
            wizard.is_create_disabled = (
                not wizard.return_type_id
                or not wizard.date_from
                or not wizard.date_to
                or wizard.show_warning_existing_return
                or wizard.show_warning_overlap
            )

    @api.onchange("return_type_id")
    def _onchange_return_type_id(self) -> None:
        today = fields.Date.context_today(self)
        if self.return_type_id:
            period_months = self.return_type_id._get_periodicity_months_delay(
                self.company_id, date=self.date_from
            )
            shifted_date = today - relativedelta(months=period_months)
            self.date_from, self.date_to = self.return_type_id._get_period_boundaries(
                self.company_id, shifted_date
            )
        else:
            self.date_from = self.date_to = False

    @api.depends("category")
    @_debug.perf.timed
    def _compute_available_return_type_ids(self) -> None:
        return_type_by_country_and_category = self.env[
            "account.return.type"
        ]._read_group(
            domain=[],
            groupby=["country_id", "category"],
            aggregates=["id:recordset"],
        )
        country_return_type_map = defaultdict(
            lambda: defaultdict(lambda: self.env["account.return.type"])
        )

        for country, category, returns in return_type_by_country_and_category:
            country_return_type_map[country][category] |= returns

        generic_tax_report = self.env.ref("account.generic_tax_report")

        for wizard in self:
            wizard_country_return_types = country_return_type_map[
                wizard.company_id.tax_config_id.account_fiscal_country_id
            ][wizard.category]

            foreign_vat_fpos_countries = (
                self.env["account.fiscal.position"]
                .search(  # noqa: E8507 -- a transient wizard opened on one company
                    [
                        *self.env["account.fiscal.position"]._check_company_domain(
                            wizard.company_id
                        ),
                        ("foreign_vat", "!=", False),
                    ]
                )
                .mapped("country_id")
            )

            foreign_return_types = self.env["account.return.type"]
            for foreign_country in foreign_vat_fpos_countries:
                foreign_return_types |= country_return_type_map[foreign_country][
                    wizard.category
                ].filtered(lambda rt: rt.report_id.root_report_id == generic_tax_report)

            return_types_without_country = country_return_type_map[
                self.env["res.country"]
            ][wizard.category]

            has_current_country_tax_return_type = wizard_country_return_types.filtered(
                lambda rt: rt.report_id.root_report_id == generic_tax_report
            )
            if has_current_country_tax_return_type:
                return_types_without_country = return_types_without_country.filtered(
                    lambda rt: rt.report_id != generic_tax_report
                )

            _debug.pipeline(
                "available_return_types_resolved",
                company=wizard.company_id,
                category=wizard.category,
                country_types=len(wizard_country_return_types),
                foreign_countries=len(foreign_vat_fpos_countries),
                foreign_types=len(foreign_return_types),
                countryless_types=len(return_types_without_country),
                generic_report_dropped=bool(has_current_country_tax_return_type),
            )
            wizard.available_return_type_ids = (
                wizard_country_return_types
                + foreign_return_types
                + return_types_without_country
            )

    def _get_return_company_and_tax_unit(self) -> tuple:
        self.check_singleton()
        all_branch_companies_with_same_vat = (
            self.company_id._get_branches_with_same_vat()
        )
        root_company = min(
            all_branch_companies_with_same_vat,
            key=lambda comp: len(comp._get_ancestor_ids(include_self=True)),
        )
        tax_unit = (
            self.env["account.tax.unit"]
            .sudo()
            .search([("company_ids", "in", root_company.ids)], limit=1)
        )
        apply_tax_unit = (
            tax_unit
            and self.return_type_id.report_id.filter_multi_company == "tax_units"
        )
        company = tax_unit.main_company_id if apply_tax_unit else root_company
        _debug.logic(
            "return_company_resolved",
            returntype=self.return_type_id,
            root_company=root_company,
            tax_unit=tax_unit,
            apply_tax_unit=bool(apply_tax_unit),
            company=company,
        )
        return company, tax_unit

    def _get_domain_existing_returns(self, company) -> list:
        self.check_singleton()
        return [
            ("company_id", "=", company.id),
            ("type_id", "=", self.return_type_id._origin.id),
            ("date_from", "<=", self.date_to),
            ("date_to", ">=", self.date_from),
        ]

    @api.depends("date_from", "date_to", "return_type_id")
    @_debug.perf.timed
    def _compute_warnings(self) -> None:
        for wizard in self:
            wizard.show_warning_wrong_dates = False
            wizard.show_warning_existing_return = False
            wizard.show_warning_overlap = False

            if (
                not wizard.date_from
                or not wizard.date_to
                or not wizard.return_type_id
                or wizard.category == "audit"
            ):
                _debug.logic(
                    "return_warnings_skipped",
                    returntype=wizard.return_type_id,
                    category=wizard.category,
                    has_dates=bool(wizard.date_from and wizard.date_to),
                )
                continue

            date_pointer = wizard.date_from
            first_period = True
            while date_pointer <= wizard.date_to:
                period_start, period_end = wizard.return_type_id._get_period_boundaries(
                    wizard.company_id, date_pointer
                )
                if first_period and wizard.date_from != period_start:
                    wizard.show_warning_wrong_dates = True
                date_pointer = period_end + relativedelta(days=1)
                first_period = False

            if date_pointer - relativedelta(days=1) != wizard.date_to:
                wizard.show_warning_wrong_dates = True

            company, _tax_unit = wizard._get_return_company_and_tax_unit()
            intersecting = (
                self.env["account.return"]
                .sudo()
                .search_fetch(  # noqa: E8507 -- a transient wizard opened on one company
                    wizard._get_domain_existing_returns(company),
                    ["date_from", "date_to"],
                )
            )
            wizard.show_warning_existing_return = any(
                (account_return.date_from, account_return.date_to)
                == (wizard.date_from, wizard.date_to)
                for account_return in intersecting
            )
            wizard.show_warning_overlap = (
                bool(intersecting) and not wizard.show_warning_existing_return
            )
            _debug.logic(
                "return_warnings_computed",
                returntype=wizard.return_type_id,
                company=company,
                intersecting=intersecting,
                wrong_dates=wizard.show_warning_wrong_dates,
                existing_return=wizard.show_warning_existing_return,
                overlap=wizard.show_warning_overlap,
            )

    @_debug.perf.timed
    def action_create_manual_account_returns(self) -> dict | None:
        _debug.lifecycle("action_create_manual_account_returns", records=self)
        self.check_singleton()

        if self.show_warning_wrong_dates and not self.env.context.get(
            "force_periodicity_violation"
        ):
            raise UserError(
                self.env._("The selected range doesn't match any fiscal period.")
            )

        if self.show_warning_existing_return:
            raise UserError(
                self.env._("A return already exists for the selected period.")
            )

        if self.show_warning_overlap:
            raise UserError(
                self.env._("The selected period overlaps a return that already exists.")
            )

        company, tax_unit = self._get_return_company_and_tax_unit()
        if not company.has_access("read"):
            raise UserError(
                self.env._(
                    "You are trying to create returns for a company you don't have access to, please select it in the company selector"
                )
            )

        returns_created = self.return_type_id.with_context(
            forced_date_from=fields.Date.to_string(self.date_from),
            forced_date_to=fields.Date.to_string(self.date_to),
            manually_created=True,
            force_periodicity_violation=self.env.context.get(
                "force_periodicity_violation", self.category == "audit"
            ),
        )._try_create_returns_for_fiscal_year(
            company,
            tax_unit,
            allow_duplicates=True,
            bypass_period_check=True,
        )
        returns_created.skipped_check_cycles = ",".join(
            v
            for k, v in {
                "regulatory_compliance": "regulatory_compliance",
                "treasury_financing": "treasury_financing",
                "purchases": "purchases",
                "operating_expenses": "operating_expenses",
                "sales": "sales",
                "inventory": "inventory",
                "fixed_assets": "fixed_assets",
                "payroll": "payroll",
                "government": "state",
                "equity": "equity",
                "other": "other",
            }.items()
            if not self[k]
        )
        returns_created.refresh_checks()
        _debug.pipeline(
            "manual_returns_created",
            tax_return=returns_created,
            category=self.category,
            count=len(returns_created),
        )
        if len(returns_created) == 1:
            action = (
                returns_created[0].action_view_account_return()
                if self.category == "account_return"
                else returns_created[0].action_view_audit_return()
            )

            return {
                "type": "ir.actions.client",
                "tag": "action_return_close_wizard",
                "params": {"next_action": action},
            }

        return None

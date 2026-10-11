from collections import defaultdict
from datetime import timedelta
from typing import Self

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, TransactionMemo
from odoo.tools.authority_keys import declare_authority_keys

from .credit_policy_rule import PROFILE_STATES
from .credit_utils import CreditRefused, CreditVerdict

declare_authority_keys(
    "account_credit", "credit_override", "skip_credit_exceeded_authorization"
)

_debug = DebugLog(__name__)

POLICY_RULE_IDS = TransactionMemo(
    "account_credit.policy_rule_ids", invalidated_by=("credit.policy.rule",)
)

EXPOSURE_FIELDS = (
    "exposure_open",
    "exposure_overdue",
    "exposure_overdue_days",
    "exposure_draft",
    "exposure_uninvoiced",
    "exposure_total",
    "collateral_amount",
    "facility_amount",
    "limit_amount",
    "limit_available",
    "limit_suggested",
)
METRIC_FIELDS = (
    "dbt_weighted",
    "late_ratio",
    "max_days_late",
    "oldest_open_days",
    "overdue_amount",
    "tenure_months",
    "purchases_12m",
    "paid_12m",
)


class CreditProfile(models.Model):
    _name = "credit.profile"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity", "mixin.scored"]
    _description = "Credit Profile"
    _order = "partner_id, company_id"
    _check_company_auto = True

    _score_line_model = "credit.score.line"

    _partner_company_uniq = models.UniqueIndex(
        "(partner_id, company_id)",
        "A customer has one credit profile per company.",
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        index=True,
        required=True,
        domain="[('parent_id', '=', False)]",
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    active = fields.Boolean(default=True)
    grade_id = fields.Many2one(
        comodel_name="credit.grade",
        tracking=True,
        help="Decided grade. Changed by a review, or lowered automatically by "
        "an event when the configuration allows.",
    )
    grade_effective_id = fields.Many2one(
        comodel_name="credit.grade",
        compute="_compute_grade_effective_id",
        store=True,
        help="The decided grade, capped by any open event that caps it.",
    )
    grade_proposed_id = fields.Many2one(
        comodel_name="credit.grade",
        compute="_compute_grade_proposed_id",
        store=True,
        help="Grade the scorecard proposes from the last metrics refresh.",
    )
    state = fields.Selection(
        selection=PROFILE_STATES,
        compute="_compute_state",
        store=True,
        tracking=True,
    )
    score = fields.Float(tracking=True)
    score_line_ids = fields.One2many(
        comodel_name="credit.score.line",
        inverse_name="subject_id",
        readonly=True,
    )
    metrics_date = fields.Datetime(readonly=True)
    dbt_weighted = fields.Float(
        string="Days Beyond Terms",
        digits=(8, 1),
        readonly=True,
        help="Days between due date and payment, weighted by amount paid, over "
        "the metrics window. Negative means paid early.",
    )
    late_ratio = fields.Float(
        digits=(5, 2),
        readonly=True,
        help="Percent of the amount paid after its due date.",
    )
    max_days_late = fields.Integer(readonly=True)
    oldest_open_days = fields.Integer(
        readonly=True,
        help="Days past due of the oldest open receivable at the last refresh.",
    )
    overdue_amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        help="Overdue receivable at the last refresh.",
    )
    tenure_months = fields.Integer(readonly=True)
    purchases_12m = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        help="Posted customer invoices, net of refunds, over the metrics window.",
    )
    paid_12m = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        help="Receivable amount settled over the metrics window; the payment "
        "behaviour measures read nothing when it is zero.",
    )
    bureau_score = fields.Integer(
        tracking=True,
        help="Score reported by the credit bureau (Buró de Crédito, Círculo de "
        "Crédito), on the bureau's own scale.",
    )
    bureau_date = fields.Date()
    fin_date = fields.Date(
        string="Financial Statements Date",
        tracking=True,
    )
    fin_total_assets = fields.Monetary(currency_field="currency_id")
    fin_current_assets = fields.Monetary(currency_field="currency_id")
    fin_current_liabilities = fields.Monetary(currency_field="currency_id")
    fin_total_liabilities = fields.Monetary(currency_field="currency_id")
    fin_retained_earnings = fields.Monetary(currency_field="currency_id")
    fin_ebit = fields.Monetary(
        string="EBIT",
        currency_field="currency_id",
    )
    fin_equity_book = fields.Monetary(
        string="Book Equity",
        currency_field="currency_id",
    )
    z_score = fields.Float(
        string="Altman Z''",
        digits=(8, 2),
        compute="_compute_z_score",
        store=True,
        help="Altman's four-ratio model for private, non-manufacturing firms: "
        "6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4. Safe above 2.6, distress below 1.1.",
    )
    exception_until = fields.Date(
        tracking=True,
        help="A dated exception lets the partner buy on credit regardless of "
        "grade and policy until this day. It is never indefinite.",
    )
    exception_reason = fields.Char(tracking=True)
    exception_user_id = fields.Many2one(comodel_name="res.users")
    exception_active = fields.Boolean(compute="_compute_exception_active")
    hold_active = fields.Boolean(
        compute="_compute_hold_active",
        store=True,
    )
    next_review_date = fields.Date(tracking=True)
    document_compliant = fields.Boolean(
        compute="_compute_document_compliant",
        store=True,
    )
    exposure_open = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_exposure",
    )
    exposure_overdue = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_exposure",
    )
    exposure_overdue_days = fields.Integer(compute="_compute_exposure")
    exposure_draft = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_exposure",
    )
    exposure_uninvoiced = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_exposure",
    )
    exposure_total = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_exposure",
    )
    collateral_amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_limit",
    )
    facility_amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_limit",
    )
    limit_amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_limit",
        help="Collateral of the valid documents the grade requires, plus every "
        "facility granting today.",
    )
    limit_available = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_limit",
    )
    limit_suggested = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_limit",
        help="Purchases over the window times the grade's percentage.",
    )
    facility_ids = fields.One2many(
        comodel_name="credit.facility",
        inverse_name="profile_id",
    )
    event_ids = fields.One2many(
        comodel_name="credit.event",
        inverse_name="profile_id",
    )
    review_ids = fields.One2many(
        comodel_name="credit.review",
        inverse_name="profile_id",
    )
    facility_count = fields.Count(count_of="facility_ids")
    event_count = fields.Count(count_of="event_ids")
    review_count = fields.Count(count_of="review_ids")
    warning = fields.Text(compute="_compute_warning")

    @api.depends(
        "fin_total_assets",
        "fin_current_assets",
        "fin_current_liabilities",
        "fin_total_liabilities",
        "fin_retained_earnings",
        "fin_ebit",
        "fin_equity_book",
    )
    def _compute_z_score(self) -> None:
        for profile in self:
            assets = profile.fin_total_assets
            liabilities = profile.fin_total_liabilities
            if not assets or not liabilities:
                profile.z_score = 0.0
                continue
            working_capital = (
                profile.fin_current_assets - profile.fin_current_liabilities
            )
            profile.z_score = (
                6.56 * working_capital / assets
                + 3.26 * profile.fin_retained_earnings / assets
                + 6.72 * profile.fin_ebit / assets
                + 1.05 * profile.fin_equity_book / liabilities
            )

    @api.depends("partner_id", "company_id")
    def _compute_display_name(self):
        multi = len(self.env.companies) > 1
        for profile in self:
            name = profile.partner_id.name or ""
            if multi:
                name = f"{name} ({profile.company_id.name})"
            profile.display_name = name

    @api.depends("event_ids.is_open", "event_ids.type_id.is_hold")
    def _compute_hold_active(self) -> None:
        for profile in self:
            profile.hold_active = any(
                event.is_open and event.type_id.is_hold for event in profile.event_ids
            )

    @api.depends("exception_until")
    @api.depends_context("today")
    def _compute_exception_active(self) -> None:
        today = fields.Date.today()
        for profile in self:
            profile.exception_active = bool(
                profile.exception_until and profile.exception_until >= today
            )

    @api.depends("grade_id", "event_ids.is_open", "event_ids.type_id.grade_cap_id")
    def _compute_grade_effective_id(self) -> None:
        for profile in self:
            grade = profile.grade_id
            for event in profile.event_ids:
                cap = event.type_id.grade_cap_id
                if (
                    event.is_open
                    and cap
                    and (not grade or cap.sequence > grade.sequence)
                ):
                    grade = cap
            profile.grade_effective_id = grade

    def _score_classification_fields(self) -> list:
        return ["grade_proposed_id"]

    @api.depends("score", "metrics_date", "company_id")
    def _compute_grade_proposed_id(self) -> None:
        for profile in self:
            profile.grade_proposed_id = (
                self.env["credit.grade"]._classify(profile.score, profile.company_id)
                if profile.metrics_date
                else False
            )

    @api.depends(
        "grade_effective_id.kind",
        "hold_active",
        "oldest_open_days",
        "overdue_amount",
    )
    def _compute_state(self):
        for profile in self:
            profile.state = profile._get_state()

    def _get_state(self):
        self.check_singleton()
        if self.hold_active:
            return "legal"
        grade = self.grade_effective_id
        config = self._config()
        material = self.overdue_amount > (config.default_materiality_amount or 0.0)
        if grade.kind == "default" or (
            material and self.oldest_open_days >= config.default_days
        ):
            return "default"
        if not grade or grade.kind == "entry":
            return "cash"
        if grade.kind == "watch" or (
            material and self.oldest_open_days >= config.watch_days
        ):
            return "watch"
        return "active"

    def _credit_status(self) -> str:
        self.check_singleton()
        if self.hold_active:
            return "legal"
        if self.exception_active:
            return "authorized"
        if self.state == "default":
            return "default"
        if self.state == "cash":
            return "cash"
        if not self.document_compliant:
            return "review"
        if self.state == "watch":
            return "watch"
        return "authorized"

    def _config(self):
        self.check_singleton()
        return self.env["credit.config"].sudo()._for(self.company_id)

    @api.depends(
        "exception_until",
        "grade_id.rule_ids.document_type_id",
        "grade_id.rule_ids.is_guarantor",
        "grade_id.rule_ids.min_quantity",
        "grade_id.rule_ids.max_quantity",
        "partner_id.credit_document_ids",
        "partner_id.credit_document_ids.document_type_id",
        "partner_id.credit_document_ids.document_type_id.has_expiration",
        "partner_id.credit_document_ids.document_type_id.has_amount",
        "partner_id.credit_document_ids.document_type_id.has_collateral",
        "partner_id.credit_document_ids.expiration_state",
        "partner_id.credit_document_ids.amount",
        "partner_id.credit_document_ids.collateral_amount",
        "partner_id.credit_document_ids.is_guarantor",
    )
    def _compute_document_compliant(self) -> None:
        for profile in self:
            profile.document_compliant = not profile._get_document_issues()

    def _get_rule_keys(self) -> set:
        self.check_singleton()
        return {
            (rule.document_type_id.id, rule.is_guarantor)
            for rule in self.grade_id.rule_ids
        }

    def _get_document_issues(self):
        self.check_singleton()
        if not self.grade_id or self.exception_active:
            return []
        rules_by_key = {
            (rule.document_type_id.id, rule.is_guarantor): rule
            for rule in self.grade_id.rule_ids
        }
        documents_by_key = defaultdict(list)
        for document in self.partner_id.credit_document_ids:
            documents_by_key[
                (document.document_type_id.id, document.is_guarantor)
            ].append(document)
        issues = []
        for key, rule in rules_by_key.items():
            matching = documents_by_key.get(key, [])
            if len(matching) < rule.min_quantity:
                issues.append(
                    {"code": "missing", "rule": rule, "quantity": rule.min_quantity}
                )
            if rule.max_quantity > 0 and len(matching) > rule.max_quantity:
                issues.append(
                    {"code": "excess", "rule": rule, "quantity": rule.max_quantity}
                )
        for document in self.partner_id.credit_document_ids:
            key = (document.document_type_id.id, document.is_guarantor)
            if key not in rules_by_key:
                continue
            details = document._get_compliance_issues()
            if details:
                issues.append(
                    {"code": "noncompliant", "document": document, "details": details}
                )
        return issues

    def _render_document_issues(self, issues):
        messages = []
        for issue in issues:
            if issue["code"] == "missing":
                rule = issue["rule"]
                messages.append(
                    self.env._(
                        "- Missing %(type)s%(guarantor)s [Minimum %(quantity)s required]",
                        type=rule.document_type_id.name,
                        guarantor=self.env._(" (Guarantor)")
                        if rule.is_guarantor
                        else "",
                        quantity=issue["quantity"],
                    )
                )
            elif issue["code"] == "excess":
                messages.append(
                    self.env._(
                        "- Too many %(type)s documents [Maximum %(quantity)s allowed]",
                        type=issue["rule"].document_type_id.name,
                        quantity=issue["quantity"],
                    )
                )
            else:
                messages.append(
                    self.env._(
                        "- '%(name)s': %(details)s",
                        name=issue["document"].name,
                        details=", ".join(issue["details"]),
                    )
                )
        return messages

    def _get_total_collateral(self):
        self.check_singleton()
        rule_keys = self._get_rule_keys()
        return sum(
            document.collateral_amount
            for document in self.partner_id.credit_document_ids
            if (document.document_type_id.id, document.is_guarantor) in rule_keys
            and not document._get_compliance_issues()
        )

    def _get_granting_facilities(self):
        today = fields.Date.today()
        return self.facility_ids.filtered(lambda f: f._is_granting(today))

    @api.depends(
        "grade_id.rule_ids",
        "grade_id.limit_pct_annual_purchases",
        "purchases_12m",
        "partner_id.credit_document_ids.collateral_amount",
        "partner_id.credit_document_ids.expiration_state",
        "facility_ids.amount",
        "facility_ids.state",
        "facility_ids.date_start",
        "facility_ids.date_end",
        "facility_ids.order_ids.state",
        "exposure_total",
    )
    def _compute_limit(self) -> None:
        for profile in self:
            profile.collateral_amount = profile._get_total_collateral()
            profile.facility_amount = sum(
                profile._get_granting_facilities().mapped("amount")
            )
            profile.limit_amount = profile.collateral_amount + profile.facility_amount
            profile.limit_available = profile.limit_amount - profile.exposure_total
            profile.limit_suggested = (
                profile.purchases_12m
                * (profile.grade_id.limit_pct_annual_purchases or 0.0)
                / 100.0
            )

    def _partner_ids_by_profile(self) -> dict:
        children = dict(
            self.env["res.partner"]
            .with_context(active_test=False)
            ._read_group(
                [("commercial_partner_id", "in", self.partner_id.ids)],
                ["commercial_partner_id"],
                ["id:array_agg"],
            )
        )
        return {
            profile: children.get(profile.partner_id, [profile.partner_id.id])
            for profile in self
        }

    @api.depends("partner_id", "company_id")
    @api.depends_context("today", "credit_exclude_order_ids", "credit_exclude_move_ids")
    def _compute_exposure(self) -> None:
        today = fields.Date.today()
        receivable = self._read_receivable_exposure(today)
        draft = self._read_draft_exposure()
        uninvoiced = self._read_uninvoiced_exposure()
        for profile in self:
            open_amount, overdue, oldest_due = receivable.get(profile, (0.0, 0.0, None))
            profile.exposure_open = open_amount
            profile.exposure_overdue = overdue
            profile.exposure_overdue_days = (
                (today - oldest_due).days if oldest_due and oldest_due < today else 0
            )
            profile.exposure_draft = draft.get(profile, 0.0)
            profile.exposure_uninvoiced = uninvoiced.get(profile, 0.0)
            profile.exposure_total = (
                open_amount + profile.exposure_draft + profile.exposure_uninvoiced
            )

    def _read_receivable_exposure(self, today):
        result = {}
        by_company = self.grouped("company_id")
        for company, profiles in by_company.items():
            partner_ids = profiles._partner_ids_by_profile()
            profile_by_partner = {
                pid: profile for profile, ids in partner_ids.items() for pid in ids
            }
            groups = (
                self.env["account.move.line"]
                .sudo()
                ._read_group(
                    [
                        ("account_id.account_type", "=", "asset_receivable"),
                        ("parent_state", "=", "posted"),
                        ("reconciled", "=", False),
                        ("company_id", "child_of", company.id),
                        ("partner_id", "in", list(profile_by_partner)),
                    ],
                    ["partner_id", "date_maturity:day"],
                    ["amount_residual:sum"],
                )
            )
            totals = defaultdict(lambda: [0.0, 0.0, None])
            for partner, due, residual in groups:
                profile = profile_by_partner.get(partner.id)
                if not profile or not residual:
                    continue
                entry = totals[profile]
                entry[0] += residual
                if due and due < today and residual > 0:
                    entry[1] += residual
                    entry[2] = min(entry[2] or due, due)
            result.update({p: tuple(v) for p, v in totals.items()})
        return result

    def _read_draft_exposure(self):
        result = {}
        for company, profiles in self.grouped("company_id").items():
            partner_ids = profiles._partner_ids_by_profile()
            profile_by_partner = {
                pid: profile for profile, ids in partner_ids.items() for pid in ids
            }
            groups = (
                self.env["account.move"]
                .sudo()
                ._read_group(
                    [
                        ("move_type", "in", ("out_invoice", "out_refund")),
                        ("state", "=", "draft"),
                        ("company_id", "child_of", company.id),
                        ("partner_id", "in", list(profile_by_partner)),
                        (
                            "id",
                            "not in",
                            list(self.env.context.get("credit_exclude_move_ids", ())),
                        ),
                    ],
                    ["partner_id"],
                    ["amount_total_signed:sum"],
                )
            )
            for partner, amount in groups:
                profile = profile_by_partner.get(partner.id)
                if profile:
                    result[profile] = result.get(profile, 0.0) + amount
        return result

    def _read_uninvoiced_exposure(self):
        return {}

    @api.depends_context("company")
    @api.depends("document_compliant", "exception_until", "hold_active", "state")
    def _compute_warning(self) -> None:
        for profile in self:
            sections = []
            issues = profile._get_document_issues()
            if issues:
                sections.append(
                    self.env._("Compliance issues found:\n")
                    + "\n".join(profile._render_document_issues(issues))
                )
            if profile.exposure_overdue:
                sections.append(
                    self.env._(
                        "Overdue receivables: %s",
                        profile.currency_id.format(profile.exposure_overdue),
                    )
                )
            profile.warning = "\n\n".join(sections) or False

    @api.constrains("partner_id")
    def _check_partner_is_commercial(self) -> None:
        for profile in self:
            if profile.partner_id.commercial_partner_id != profile.partner_id:
                raise ValidationError(
                    self.env._(
                        "A credit profile belongs to the commercial partner; "
                        "record it on '%s'.",
                        profile.partner_id.commercial_partner_id.name,
                    )
                )

    @api.constrains("exception_until", "company_id")
    def _check_exception_until(self) -> None:
        today = fields.Date.today()
        for profile in self.filtered("exception_until"):
            longest = today + timedelta(days=profile._config().exception_max_days)
            if profile.exception_until > longest:
                raise ValidationError(
                    self.env._(
                        "An exception may run at most %(days)s days, until %(date)s.",
                        days=profile._config().exception_max_days,
                        date=longest,
                    )
                )
            if profile.hold_active:
                raise ValidationError(
                    self.env._(
                        "Cannot grant an exception to '%s': a hold is open.",
                        profile.partner_id.name,
                    )
                )

    @api.model
    def _for_partner(self, partner, company=None, create=False):
        partner = partner.commercial_partner_id
        company = company or self.env.company
        if not partner:
            return self.browse()
        profile = self._for_partners(partner, company).get(partner.id, self.browse())
        if profile or not create:
            return profile.with_env(self.env)
        config = self.env["credit.config"].sudo()._for(company)
        return (
            self.sudo()
            .create(
                {
                    "partner_id": partner.id,
                    "company_id": company.id,
                    "grade_id": config.entry_grade_id.id,
                }
            )
            .with_env(self.env)
        )

    @api.model
    def _for_partners(self, partners, company) -> dict:
        if not (commercial := partners.commercial_partner_id):
            return {}
        profiles = self.sudo().search(
            [("partner_id", "in", commercial.ids), ("company_id", "=", company.id)]
        )
        by_partner = {}
        for profile in profiles.with_env(self.env):
            by_partner.setdefault(profile.partner_id.id, profile)
        return by_partner

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "grade_id" not in vals:
                company = self.env["res.company"].browse(
                    vals.get("company_id", self.env.company.id)
                )
                vals["grade_id"] = (
                    self.env["credit.config"].sudo()._for(company).entry_grade_id.id
                )
        profiles = super().create(vals_list)
        profiles._sync_partner_credit_limit()
        return profiles

    def write(self, vals):
        if "grade_id" in vals and not self.env.su:
            if not self.env.user.has_group("account_credit.group_credit_user"):
                raise ValidationError(
                    self.env._("Only a credit user can change a partner's grade.")
                )
        manager_fields = {"exception_until", "exception_reason"}
        if manager_fields & set(vals) and not self.env.su:
            if not self.env.user.has_group("account_credit.group_credit_manager"):
                raise ValidationError(
                    self.env._("Only a credit manager can grant or end an exception.")
                )
        old_grades = {profile: profile.grade_id for profile in self}
        if vals.get("exception_until"):
            vals = dict(vals, exception_user_id=self.env.user.id)
        result = super().write(vals)
        if "grade_id" in vals:
            for profile in self:
                if old_grades[profile] != profile.grade_id:
                    profile._record_event(
                        "grade_changed",
                        note=self.env._(
                            "%(old)s -> %(new)s",
                            old=old_grades[profile].name or "-",
                            new=profile.grade_id.name or "-",
                        ),
                        extra={
                            "grade_from_id": old_grades[profile].id,
                            "grade_to_id": profile.grade_id.id,
                        },
                    )
        if "exception_until" in vals:
            for profile in self:
                profile._record_event(
                    "exception_granted"
                    if vals["exception_until"]
                    else "exception_ended",
                    note=vals.get("exception_reason") or profile.exception_reason,
                )
        self._sync_partner_credit_limit()
        return result

    def _sync_partner_credit_limit(self) -> None:
        for profile in self:
            partner = profile.partner_id.sudo().with_company(profile.company_id)
            partner.invalidate_recordset(["credit_limit"])
            partner.modified(["credit_limit"])
            partner._compute_credit_limit()

    def _on_facilities_changed(self) -> None:
        self.invalidate_recordset(
            ["facility_amount", "limit_amount", "limit_available", "collateral_amount"]
        )
        self._sync_partner_credit_limit()

    def _on_events_changed(self) -> None:
        self.modified(["event_ids"])
        self.invalidate_recordset(["hold_active", "grade_effective_id", "state"])

    def _record_event(
        self,
        code,
        amount=0.0,
        note=None,
        res=None,
        amount_by_profile=None,
        extra=None,
    ):
        event_type = self.env["credit.event.type"].search(
            [("code", "=", code)], limit=1
        )
        if not event_type:
            _debug.logic("event_type_missing", code=code)
            return self.env["credit.event"]
        vals_list = []
        for profile in self:
            vals = {
                "profile_id": profile.id,
                "type_id": event_type.id,
                "amount": (amount_by_profile or {}).get(profile, amount),
                "note": note,
            }
            if res is not None:
                vals.update(res_model=res._name, res_id=res.id)
            if extra:
                vals.update(extra)
            vals_list.append(vals)
        return self.env["credit.event"].sudo().create(vals_list)

    def _open_events(self, code):
        self.check_singleton()
        return self.event_ids.filtered(lambda e: e.is_open and e.code == code)

    def _open_review(self, kind, trigger_event=None):
        self.check_singleton()
        open_review = self.review_ids.filtered(
            lambda r: r.state in ("draft", "in_progress")
        )
        if open_review:
            return open_review[:1]
        config = self._config()
        return (
            self.env["credit.review"]
            .sudo()
            .create(
                {
                    "profile_id": self.id,
                    "kind": kind,
                    "user_id": config.review_user_id.id or self.env.user.id,
                    "trigger_event_id": trigger_event.id if trigger_event else False,
                }
            )
        )

    def _term_days(self, payment_term):
        if not payment_term:
            return 0
        return max(
            (
                line.nb_days
                + (
                    30
                    if line.delay_type
                    in (
                        "days_after_end_of_month",
                        "days_after_end_of_next_month",
                        "days_end_of_month_on_the",
                    )
                    else 0
                )
                for line in payment_term.line_ids
            ),
            default=0,
        )

    def _facts(self, kind, amount, immediate, term_days) -> dict:
        self.check_singleton()
        limit = self.limit_amount
        exposure = self.exposure_total + self.env.context.get(
            "credit_extra_exposure", 0.0
        )
        uses_limit = bool(self.grade_id) and (
            self.grade_id.kind != "entry"
            or self.exception_active
            or bool(self._get_granting_facilities())
        )
        excess = max(0.0, exposure + amount - limit) if uses_limit else 0.0
        return {
            "kind": kind,
            "amount": amount,
            "immediate": immediate,
            "term_days": term_days if term_days is not None else 0,
            "hold": self.hold_active,
            "exception": self.exception_active,
            "overdue": self.exposure_overdue,
            "overdue_days": self.exposure_overdue_days,
            "exposure": exposure,
            "limit": limit,
            "excess": excess,
        }

    def _invalidate_exposure(self) -> Self:
        self.invalidate_recordset(EXPOSURE_FIELDS)
        return self

    def _evaluate(
        self, kind, amount=0.0, immediate=False, term_days=None, *, refresh=True
    ):
        if not self:
            _debug.logic("credit_no_standing", kind=kind)
            return CreditVerdict()
        self.check_singleton()
        if refresh:
            self._invalidate_exposure()
        facts = self.sudo()._facts(kind, amount, immediate, term_days)
        verdict = CreditVerdict(
            exposure=facts["exposure"], limit=facts["limit"], excess=facts["excess"]
        )
        rules = self._policy_rules()
        profile = self.sudo()
        for rule in rules:
            if not rule._applies(profile, facts):
                continue
            verdict.add(
                rule.outcome, rule._render(profile, facts), rule.id, rule.condition
            )
            if rule.stop:
                break
        _debug.logic(
            "credit_verdict",
            profile=self,
            kind=kind,
            amount=amount,
            immediate=immediate,
            outcome=verdict.outcome,
            rules=verdict.rule_ids,
        )
        return verdict

    def _policy_rules(self):
        rule_ids_by_company = POLICY_RULE_IDS(self.env)
        company_id = self.company_id.id
        Rule = self.env["credit.policy.rule"].sudo()
        key = (company_id, self.env.context.get("active_test", True))
        if (rule_ids := rule_ids_by_company.get(key)) is None:
            rule_ids = rule_ids_by_company[key] = Rule.search(
                [("company_id", "in", [False, company_id])]
            ).ids
        return Rule.browse(rule_ids)

    def _credit_override(self) -> bool:
        context = self.env.context
        return bool(
            context.get("credit_override")
            or context.get("skip_credit_exceeded_authorization")
        )

    def _check_credit(
        self,
        kind,
        amount=0.0,
        immediate=False,
        term_days=None,
        approval_exempt=(),
        *,
        refresh=True,
    ):
        if self.env.context.get("install_module"):
            return CreditVerdict()
        verdict = self._evaluate(kind, amount, immediate, term_days, refresh=refresh)
        if verdict.blocked:
            raise CreditRefused(
                self.env._(
                    "Credit refused for '%(partner)s':\n%(reasons)s",
                    partner=self.partner_id.name,
                    reasons=verdict.message(),
                ),
                verdict,
            )
        if (
            verdict.is_approval_required_except(approval_exempt)
            and not self._credit_override()
        ):
            raise CreditRefused(
                self.env._(
                    "Credit for '%(partner)s' needs a credit manager's authorization:\n"
                    "%(reasons)s",
                    partner=self.partner_id.name,
                    reasons=verdict.message(),
                ),
                verdict,
            )
        return verdict

    def _update_metrics(self) -> None:
        if not self:
            return
        self._invalidate_exposure()
        now = fields.Datetime.now()
        today = fields.Date.today()
        for company, profiles in self.grouped("company_id").items():
            config = self.env["credit.config"].sudo()._for(company)
            since = today - relativedelta(months=config.metrics_window_months)
            behaviour = profiles._read_payment_behaviour(company, since)
            purchases = profiles._read_purchases(company, since)
            for profile in profiles:
                dbt, late_ratio, max_late, paid = behaviour.get(
                    profile, (0.0, 0.0, 0, 0.0)
                )
                bought, first_invoice = purchases.get(profile, (0.0, None))
                tenure = (
                    (today.year - first_invoice.year) * 12
                    + today.month
                    - first_invoice.month
                    if first_invoice
                    else 0
                )
                profile.write(
                    {
                        "dbt_weighted": dbt,
                        "late_ratio": late_ratio,
                        "max_days_late": max_late,
                        "oldest_open_days": profile.exposure_overdue_days,
                        "overdue_amount": profile.exposure_overdue,
                        "tenure_months": tenure,
                        "purchases_12m": bought,
                        "paid_12m": paid,
                        "metrics_date": now,
                    }
                )
        self._score_refresh()

    def _read_payment_behaviour(self, company, since) -> dict:
        partner_ids = self._partner_ids_by_profile()
        profile_by_partner = {
            pid: profile for profile, ids in partner_ids.items() for pid in ids
        }
        if not profile_by_partner:
            return {}
        self.env["account.move.line"].flush_model(
            ["account_id", "company_id", "partner_id", "date_maturity", "parent_state"]
        )
        self.env["account.partial.reconcile"].flush_model(
            ["debit_move_id", "amount", "max_date"]
        )
        self.env["account.account"].flush_model(["account_type"])
        self.env.cr.execute(
            SQL(
                """
                SELECT l.partner_id,
                       SUM((pr.max_date - l.date_maturity) * pr.amount) AS weighted_days,
                       SUM(pr.amount) AS paid,
                       SUM(pr.amount) FILTER (WHERE pr.max_date > l.date_maturity) AS paid_late,
                       MAX(pr.max_date - l.date_maturity) AS max_late
                  FROM account_partial_reconcile pr
                  JOIN account_move_line l ON l.id = pr.debit_move_id
                  JOIN account_account a ON a.id = l.account_id
                 WHERE a.account_type = 'asset_receivable'
                   AND l.parent_state = 'posted'
                   AND l.company_id = ANY(%s)
                   AND l.partner_id = ANY(%s)
                   AND l.date_maturity IS NOT NULL
                   AND pr.max_date >= %s
                 GROUP BY l.partner_id
                """,
                self.env["res.company"].search([("id", "child_of", company.id)]).ids,
                list(profile_by_partner),
                since,
            )
        )
        totals = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
        for partner_id, weighted, paid, paid_late, max_late in self.env.cr.fetchall():
            entry = totals[profile_by_partner[partner_id]]
            entry[0] += weighted or 0.0
            entry[1] += paid or 0.0
            entry[2] += paid_late or 0.0
            entry[3] = max(entry[3], max_late or 0)
        return {
            profile: (
                round(weighted / paid, 1) if paid else 0.0,
                round(100.0 * late / paid, 2) if paid else 0.0,
                max_late,
                paid,
            )
            for profile, (weighted, paid, late, max_late) in totals.items()
        }

    def _read_purchases(self, company, since):
        partner_ids = self._partner_ids_by_profile()
        profile_by_partner = {
            pid: profile for profile, ids in partner_ids.items() for pid in ids
        }
        result = {}
        Move = self.env["account.move"].sudo()
        domain = [
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("company_id", "child_of", company.id),
            ("partner_id", "in", list(profile_by_partner)),
        ]
        for partner, first in Move._read_group(
            domain, ["partner_id"], ["invoice_date:min"]
        ):
            profile = profile_by_partner[partner.id]
            bought, oldest = result.get(profile, (0.0, None))
            result[profile] = (bought, min(oldest or first, first) if first else oldest)
        for partner, amount in Move._read_group(
            domain + [("invoice_date", ">=", since)],
            ["partner_id"],
            ["amount_total_signed:sum"],
        ):
            profile = profile_by_partner[partner.id]
            bought, oldest = result.get(profile, (0.0, None))
            result[profile] = (bought + (amount or 0.0), oldest)
        return result


    def _score_observe_dbt(self, dimension):
        self.check_singleton()
        return self.dbt_weighted if self.paid_12m else None

    def _score_observe_late_ratio(self, dimension):
        self.check_singleton()
        return self.late_ratio if self.paid_12m else None

    def _score_observe_max_days_late(self, dimension):
        self.check_singleton()
        return float(self.max_days_late) if self.paid_12m else None

    def _score_observe_oldest_open_days(self, dimension) -> float:
        self.check_singleton()
        return float(self.oldest_open_days)

    def _score_observe_tenure_months(self, dimension) -> float:
        self.check_singleton()
        return float(self.tenure_months)

    def _score_observe_collateral_coverage(self, dimension):
        self.check_singleton()
        if not self.exposure_total:
            return 100.0
        return 100.0 * self.collateral_amount / self.exposure_total

    def _score_observe_document_compliance(self, dimension):
        self.check_singleton()
        return 100.0 if self.document_compliant else 0.0

    def _score_observe_bureau_score(self, dimension):
        self.check_singleton()
        return float(self.bureau_score) if self.bureau_score else None

    def _score_observe_z_score(self, dimension):
        self.check_singleton()
        return (
            self.z_score
            if self.fin_total_assets and self.fin_total_liabilities
            else None
        )

    def action_refresh_metrics(self) -> None:
        self._update_metrics()

    def action_grant_exception(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Grant a Dated Exception"),
            "res_model": "wizard.credit.profile.grant.exception",
            "view_mode": "form",
            "target": "new",
            "context": {"default_profile_id": self.id},
        }

    def action_end_exception(self) -> None:
        self.write({"exception_until": False})

    def action_toggle_legal(self) -> None:
        self.check_singleton()
        if not self.env.su and not self.env.user.has_group(
            "account_credit.group_credit_manager"
        ):
            raise AccessError(
                self.env._("Only a credit manager can send a partner to legal process.")
            )
        open_holds = self._open_events("legal_hold")
        if open_holds:
            open_holds.action_lift()
            return
        if self.exception_active:
            self.sudo().write({"exception_until": False})
        self._record_event("legal_hold")

    def action_open_review(self) -> dict:
        self.check_singleton()
        review = self._open_review("manual")
        return {
            "type": "ir.actions.act_window",
            "res_model": "credit.review",
            "res_id": review.id,
            "view_mode": "form",
        }

    def action_view_facilities(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Credit Facilities"),
            "res_model": "credit.facility",
            "view_mode": "list,form",
            "domain": [("profile_id", "=", self.id)],
            "context": {"default_profile_id": self.id},
        }

    def action_view_events(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Credit Events"),
            "res_model": "credit.event",
            "view_mode": "list,form",
            "domain": [("profile_id", "=", self.id)],
            "context": {"default_profile_id": self.id},
        }

    def action_view_reviews(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Credit Reviews"),
            "res_model": "credit.review",
            "view_mode": "list,form",
            "domain": [("profile_id", "=", self.id)],
            "context": {"default_profile_id": self.id},
        }

    @api.model
    def _cron_refresh(self) -> None:
        profiles = self.search([])
        profiles._update_metrics()
        profiles._detect_events()
        profiles._expire_exceptions()
        profiles._schedule_reviews()

    def _detect_events(self) -> None:
        for profile in self:
            config = profile._config()
            material = profile.overdue_amount > (
                config.default_materiality_amount or 0.0
            )
            in_default = material and profile.oldest_open_days >= config.default_days
            open_default = profile._open_events("overdue_default")
            if in_default and not open_default:
                profile._record_event("overdue_default", amount=profile.overdue_amount)
            elif open_default and not in_default:
                open_default.sudo().write(
                    {
                        "lifted_on": fields.Datetime.now(),
                        "lifted_by_id": self.env.user.id,
                    }
                )
                profile._on_events_changed()
                profile._record_event("payment_recovered")
            if (
                config.auto_downgrade
                and profile.grade_proposed_id
                and profile.grade_proposed_id.kind != "default"
                and profile.grade_id
                and profile.grade_id.kind != "entry"
                and profile.grade_proposed_id.sequence > profile.grade_id.sequence
            ):
                profile.sudo().write({"grade_id": profile.grade_proposed_id.id})

    def _expire_exceptions(self) -> None:
        today = fields.Date.today()
        expired = self.filtered(
            lambda p: p.exception_until and p.exception_until < today
        )
        for profile in expired:
            if profile._open_events("exception_expired"):
                continue
            profile._record_event("exception_expired", note=profile.exception_reason)
            profile.sudo().write({"exception_until": False})

    def _schedule_reviews(self) -> None:
        today = fields.Date.today()
        for profile in self:
            if profile.next_review_date and profile.next_review_date <= today:
                profile._open_review("periodic")


class CreditScoreLine(models.Model):
    _name = "credit.score.line"
    _inherit = ["mixin.score.line"]
    _description = "Credit Score Line"
    _order = "subject_id, dimension_id, id"

    subject_id = fields.Many2one(
        comodel_name="credit.profile",
        string="Profile",
        index=True,
        required=True,
        ondelete="cascade",
    )

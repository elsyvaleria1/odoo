from collections.abc import Collection
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog

from .credit_utils import CreditRefused

_debug = DebugLog(__name__)

CREDIT_STATUS = [
    ("cash", "Cash Only"),
    ("review", "Under Review"),
    ("authorized", "Credit Authorized"),
    ("watch", "Watch"),
    ("default", "Default"),
    ("legal", "Legal Process"),
]


class Partner(models.Model):
    _inherit = "res.partner"

    credit_profile_id = fields.Many2one(
        comodel_name="credit.profile",
        compute="_compute_credit_profile_id",
        search="_search_credit_profile_id",
        groups="account_credit.group_credit_readonly",
    )
    credit_profile_ids = fields.One2many(
        comodel_name="credit.profile",
        inverse_name="partner_id",
        string="Credit Profiles per Company",
        groups="account_credit.group_credit_readonly",
    )
    credit_grade_id = fields.Many2one(
        comodel_name="credit.grade",
        compute="_compute_credit_grade_id",
        inverse="_inverse_credit_grade_id",
        help="Grade of this partner's credit profile in the current company.",
    )
    credit_status = fields.Selection(
        selection=CREDIT_STATUS,
        compute="_compute_credit_status",
        inverse="_inverse_credit_status",
        search="_search_credit_status",
        help="Operational standing of the credit profile in the current company, "
        "empty while the partner has none: no credit check applies to a partner "
        "without a profile. Writing it is a shortcut: cash assigns the entry "
        "grade, legal opens a hold, review assigns a grade whose documents are "
        "missing, authorized a performing grade without document rules.",
    )
    credit_exception = fields.Boolean(
        compute="_compute_credit_exception",
        inverse="_inverse_credit_exception",
        help="A dated exception is running on the profile. Setting it grants an "
        "exception for the company's maximum; clearing it ends the exception.",
    )
    credit_exception_until = fields.Date(compute="_compute_credit_fields")
    credit_legal_hold = fields.Boolean(
        compute="_compute_credit_legal_hold",
        inverse="_inverse_credit_legal_hold",
    )
    credit_document_compliant = fields.Boolean(compute="_compute_credit_fields")
    credit_trusted_amount = fields.Float(
        compute="_compute_credit_trusted_amount",
        inverse="_inverse_credit_trusted_amount",
        groups="account_credit.group_credit_readonly",
        help="Manually granted facilities in the current company, in total.",
    )
    credit_type_warning = fields.Text(compute="_compute_credit_fields")
    credit_limit = fields.Float(
        compute="_compute_credit_limit",
        store=True,
        copy=False,
        readonly=True,
        company_dependent=True,
        tracking=True,
        groups="account_credit.group_credit_readonly,"
        "account_credit.privilege_read_credit_limit",
        help="Receivable limit specific to this partner: the collateral of the "
        "valid documents its grade requires, plus every facility granting today.",
    )
    show_credit_limit = fields.Boolean(
        groups="account.group_account_invoice,account.group_account_readonly,"
        "account_credit.group_credit_readonly"
    )
    use_partner_credit_limit = fields.Boolean(
        compute_sudo=True,
        groups="account.group_account_invoice,account.group_account_readonly,"
        "account_credit.group_credit_readonly",
    )
    user_credit_manager = fields.Boolean(compute="_compute_credit_groups")
    user_credit_user = fields.Boolean(compute="_compute_credit_groups")
    credit_document_ids = fields.One2many(
        comodel_name="document.document",
        inverse_name="partner_id",
        copy=False,
        domain=lambda self: self._domain_credit_document_ids(),
        help="Documents submitted for credit evaluation: this partner's own "
        "documents that live under the company's credit folder, plus those "
        "of a type a credit grade requires wherever they are filed. Derived "
        "from the documents themselves, so it is never stale.",
    )

    credit_root_folder_id = fields.Many2one(
        comodel_name="document.document",
        compute="_compute_credit_root_folder_id",
        help=(
            "The active company's root credit folder, mirrored from Settings "
            "so the Credit tab can file a new document into it. There is no "
            "folder per partner: which partner a document belongs to is "
            "``partner_id``, not where it was dropped."
        ),
    )

    def _compute_credit_root_folder_id(self) -> None:
        folder = self.env.company.sudo().credit_folder_id
        for partner in self:
            partner.credit_root_folder_id = folder

    def _domain_credit_document_ids(self):
        scope = self.env["credit.config"].with_privilege(
            "account_credit.privilege_read_credit_file_scope",
            reason="a credit file holds the same documents whoever reads it",
        )
        roots = scope.search([("credit_folder_id", "!=", False)]).credit_folder_id
        required_types = scope.env["credit.grade.rule"].search([]).document_type_id
        if not roots and not required_types:
            return Domain.FALSE
        filed = Domain.OR(Domain("folder_id", "child_of", root.id) for root in roots)
        if required_types:
            filed |= Domain("document_type_id", "in", required_types.ids)
        return filed & Domain("type", "!=", "folder")

    @api.model
    def _commercial_fields(self):
        fields_ = super()._commercial_fields()
        if "credit_limit" in fields_:
            fields_.remove("credit_limit")
        return fields_

    @api.depends_context("company")
    @api.depends(
        "commercial_partner_id", "commercial_partner_id.credit_profile_ids.company_id"
    )
    def _compute_credit_profile_id(self) -> None:
        Profile = self.env["credit.profile"].sudo()
        commercial = self.commercial_partner_id
        profiles = Profile.search(
            [
                ("partner_id", "in", commercial.ids),
                ("company_id", "=", self.env.company.id),
            ]
        )
        by_partner = {profile.partner_id: profile for profile in profiles}
        for partner in self:
            partner.credit_profile_id = by_partner.get(partner.commercial_partner_id)

    def _search_credit_profile_id(self, operator, value) -> list:
        profiles = self.env["credit.profile"].sudo()
        if operator in ("any", "not any"):
            profiles = profiles.search(
                Domain(value) & Domain("company_id", "=", self.env.company.id)
            )
        else:
            profiles = profiles.search(
                [("id", operator, value), ("company_id", "=", self.env.company.id)]
            )
        negate = operator in ("not any", "not in", "!=")
        return [
            (
                "commercial_partner_id",
                "not in" if negate else "in",
                profiles.partner_id.ids,
            )
        ]

    def _credit_profile_sudo(self):
        self.check_singleton()
        return self.sudo().credit_profile_id

    @api.depends_context("company")
    @api.depends(
        "commercial_partner_id", "commercial_partner_id.credit_profile_ids.grade_id"
    )
    def _compute_credit_grade_id(self) -> None:
        for partner in self:
            partner.credit_grade_id = partner._credit_profile_sudo().grade_id

    @api.depends_context("company", "today")
    @api.depends(
        "commercial_partner_id",
        "commercial_partner_id.credit_profile_ids.exception_until",
    )
    def _compute_credit_exception(self) -> None:
        for partner in self:
            profile = partner._credit_profile_sudo()
            partner.credit_exception = profile.exception_active

    @api.depends_context("company")
    @api.depends(
        "commercial_partner_id",
        "commercial_partner_id.credit_profile_ids.hold_active",
        "commercial_partner_id.credit_profile_ids.event_ids.is_open",
    )
    def _compute_credit_legal_hold(self) -> None:
        for partner in self:
            partner.credit_legal_hold = partner._credit_profile_sudo().hold_active

    @api.depends_context("company", "today")
    @api.depends(
        "commercial_partner_id",
        "commercial_partner_id.credit_profile_ids.facility_ids.amount",
        "commercial_partner_id.credit_profile_ids.facility_ids.state",
        "commercial_partner_id.credit_profile_ids.facility_ids.date_end",
    )
    def _compute_credit_trusted_amount(self) -> None:
        for partner in self:
            profile = partner._credit_profile_sudo()
            partner.credit_trusted_amount = sum(
                profile._get_granting_facilities()
                .filtered(lambda f: f.source == "manual")
                .mapped("amount")
            )

    @api.depends_context("company", "today")
    @api.depends(
        "commercial_partner_id",
        "commercial_partner_id.credit_profile_ids.grade_id",
        "commercial_partner_id.credit_profile_ids.state",
        "commercial_partner_id.credit_profile_ids.exception_until",
        "commercial_partner_id.credit_profile_ids.hold_active",
        "commercial_partner_id.credit_profile_ids.document_compliant",
        "commercial_partner_id.credit_profile_ids.event_ids.is_open",
    )
    def _compute_credit_status(self) -> None:
        for partner in self:
            profile = partner._credit_profile_sudo()
            partner.credit_status = profile._credit_status() if profile else False

    @api.depends_context("company", "today")
    @api.depends(
        "commercial_partner_id",
        "commercial_partner_id.credit_profile_ids.grade_id",
        "commercial_partner_id.credit_profile_ids.exception_until",
        "commercial_partner_id.credit_profile_ids.document_compliant",
        "commercial_partner_id.credit_document_ids.expiration_state",
        "commercial_partner_id.credit_document_ids.amount",
        "commercial_partner_id.credit_document_ids.collateral_amount",
    )
    def _compute_credit_fields(self) -> None:
        for partner in self:
            profile = partner._credit_profile_sudo()
            partner.credit_exception_until = profile.exception_until
            partner.credit_document_compliant = (
                profile.document_compliant if profile else True
            )
            partner.credit_type_warning = profile.warning if profile else False

    def _get_credit_profile(self, create=True):
        self.check_singleton()
        return (
            self.env["credit.profile"]
            .sudo()
            ._for_partner(self, company=self.env.company, create=create)
        )

    def _search_credit_status(self, operator, value):
        values = (
            value
            if isinstance(value, Collection) and not isinstance(value, str)
            else [value]
        )
        profiles = (
            self.env["credit.profile"]
            .sudo()
            .search([("company_id", "=", self.env.company.id)])
        )
        matching = profiles.filtered(lambda p: p._credit_status() in values)
        domain = Domain("commercial_partner_id", "in", matching.partner_id.ids)
        if False in values:
            domain |= Domain("commercial_partner_id", "not in", profiles.partner_id.ids)
        return ~domain if operator in ("!=", "not in") else domain

    def _inverse_credit_status(self) -> None:
        Grade = self.env["credit.grade"].sudo()
        for partner in self:
            status = partner.credit_status
            if not status:
                continue
            profile = partner._get_credit_profile()
            if status == "legal":
                if not profile.hold_active:
                    profile.action_toggle_legal()
                continue
            if profile.hold_active:
                profile.action_toggle_legal()
            if status == "cash":
                profile.write({"grade_id": profile._config().entry_grade_id.id})
            elif status == "authorized":
                grade = Grade.search(
                    [("kind", "=", "performing"), ("rule_ids", "=", False)],
                    order="sequence",
                    limit=1,
                ) or Grade.create({"name": "Authorized without documents"})
                profile.write({"grade_id": grade.id})
            elif status == "review":
                grade = Grade.search(
                    [("kind", "=", "performing"), ("rule_ids", "!=", False)],
                    order="sequence desc",
                    limit=1,
                )
                if grade:
                    profile.write({"grade_id": grade.id})

    def _get_default_credit_type(self):
        return self.env["credit.config"].sudo()._for(self.env.company).entry_grade_id

    def _get_overdue_receivable_summary(self) -> str | None:
        self.check_singleton()
        overdue = self._get_live_overdue_amount()
        if not overdue:
            return None
        return self.env._(
            "Overdue receivables: %s", self.env.company.currency_id.format(overdue)
        )

    def _check_credit_allowed(
        self, immediate, kind="order", amount=0.0, term_days=None
    ) -> None:
        self.check_singleton()
        if self.env.context.get("install_module"):
            return
        profile = self.commercial_partner_id._get_credit_profile(create=False)
        verdict = profile._evaluate(
            kind, amount=amount, immediate=immediate, term_days=term_days
        )
        if verdict.blocked:
            raise CreditRefused(
                self.env._(
                    "Credit refused for '%(partner)s':\n%(reasons)s",
                    partner=self.name,
                    reasons=verdict.message(),
                ),
                verdict,
            )

    def _check_credit_write_access(self, vals) -> None:
        if self.env.su:
            return
        if {"credit_exception", "credit_legal_hold", "credit_trusted_amount"} & set(
            vals
        ) and not self.env.user.has_group("account_credit.group_credit_manager"):
            raise AccessError(
                self.env._(
                    "Only a credit manager can change a partner's credit standing."
                )
            )
        if "credit_grade_id" in vals and not self.env.user.has_group(
            "account_credit.group_credit_user"
        ):
            raise AccessError(
                self.env._("Only a credit user can assign a partner's credit grade.")
            )

    def _inverse_credit_grade_id(self) -> None:
        for partner in self:
            profile = partner._get_credit_profile()
            if profile.grade_id != partner.credit_grade_id:
                profile.sudo().write({"grade_id": partner.credit_grade_id.id})

    def _inverse_credit_exception(self) -> None:
        today = fields.Date.today()
        for partner in self:
            profile = partner._get_credit_profile()
            if partner.credit_exception and not profile.exception_active:
                until = today + timedelta(days=profile._config().exception_max_days)
                profile.sudo().write(
                    {
                        "exception_until": until,
                        "exception_reason": profile.exception_reason
                        or self.env._("Granted from the partner form"),
                    }
                )
            elif not partner.credit_exception and profile.exception_active:
                profile.sudo().write({"exception_until": False})

    def _inverse_credit_legal_hold(self) -> None:
        for partner in self:
            profile = partner._get_credit_profile()
            if partner.credit_legal_hold != profile.hold_active:
                profile.sudo().action_toggle_legal()

    def _inverse_credit_trusted_amount(self) -> None:
        for partner in self:
            profile = partner._get_credit_profile()
            manual = profile.facility_ids.filtered(
                lambda f: f.source == "manual" and f.state == "active"
            )
            current = sum(manual.mapped("amount"))
            if (
                profile.currency_id.compare_amounts(
                    current, partner.credit_trusted_amount
                )
                == 0
            ):
                continue
            if manual:
                manual.sudo().write({"state": "revoked"})
            if partner.credit_trusted_amount > 0:
                self.env["credit.facility"].sudo().create(
                    {
                        "profile_id": profile.id,
                        "source": "manual",
                        "amount": partner.credit_trusted_amount,
                        "reason": self.env._("Standing allowance"),
                        "user_id": self.env.user.id,
                    }
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_credit_write_access(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_credit_write_access(vals)
        m2m_value = vals.get("credit_document_ids")
        owner_adds, child_commands = self._split_credit_document_commands(m2m_value)
        if not owner_adds:
            return super().write(vals)
        children = self.filtered(lambda p: p.commercial_partner_id != p)
        if not children:
            return super().write(vals)
        child_vals = dict(vals)
        if child_commands:
            child_vals["credit_document_ids"] = child_commands
        else:
            child_vals.pop("credit_document_ids")
        non_children = self - children
        owners = children.commercial_partner_id - non_children
        result = True
        if owners:
            owners.write({"credit_document_ids": owner_adds})
        if non_children:
            result = super(Partner, non_children).write(vals)
        return super(Partner, children).write(child_vals) and result

    @api.model
    def _split_credit_document_commands(self, value) -> tuple:
        if not value:
            return [], []
        if isinstance(value, models.BaseModel):
            value = [Command.set(value.ids)]
        elif isinstance(value, tuple) or (
            isinstance(value, list) and not isinstance(value[0], (tuple, list))
        ):
            value = [Command.set(list(value))]
        owner_adds, child_commands = [], []
        for command in value:
            code = command[0]
            if code in (Command.CREATE, Command.LINK):
                owner_adds.append(command)
            elif code == Command.SET:
                owner_adds.extend(Command.link(doc_id) for doc_id in command[2])
                child_commands.append(Command.clear())
            else:
                child_commands.append(command)
        return owner_adds, child_commands

    @api.depends_context("uid")
    def _compute_credit_groups(self) -> None:
        is_manager = self.env.user.has_group("account_credit.group_credit_manager")
        is_user = is_manager or self.env.user.has_group(
            "account_credit.group_credit_user"
        )
        for partner in self:
            partner.user_credit_manager = is_manager
            partner.user_credit_user = is_user

    @api.depends_context("company")
    @api.depends("credit_profile_ids.grade_id", "credit_profile_ids.facility_ids")
    def _compute_use_partner_credit_limit(self) -> None:
        super()._compute_use_partner_credit_limit()
        for partner in self:
            profile = partner.sudo().credit_profile_id
            if profile.grade_id and profile.grade_id.kind != "entry":
                partner.use_partner_credit_limit = True

    def _inverse_use_partner_credit_limit(self) -> None:
        without_profile = self.filtered(
            lambda p: not p.sudo().credit_profile_id.grade_id
        )
        if without_profile:
            super(Partner, without_profile)._inverse_use_partner_credit_limit()

    @api.depends(
        "credit_profile_ids.grade_id",
        "credit_profile_ids.grade_id.rule_ids.document_type_id",
        "credit_profile_ids.grade_id.rule_ids.is_guarantor",
        "credit_profile_ids.exception_until",
        "credit_profile_ids.facility_ids.amount",
        "credit_profile_ids.facility_ids.state",
        "credit_profile_ids.facility_ids.date_end",
        "credit_profile_ids.facility_ids.order_ids.state",
        "credit_document_ids.collateral_amount",
        "credit_document_ids.expiration_state",
        "credit_document_ids.document_type_id",
        "credit_document_ids.is_guarantor",
    )
    def _compute_credit_limit(self) -> None:
        for partner in self:
            commercial = partner.commercial_partner_id
            profiles = commercial.sudo().credit_profile_ids
            if not profiles:
                partner.credit_limit = partner.credit_limit or 0.0
                continue
            for profile in profiles:
                scoped = partner.with_company(profile.company_id)
                scoped.credit_limit = (
                    profile.limit_amount if commercial == partner else 0.0
                )

    def action_toggle_legal(self) -> None:
        self.check_singleton()
        if not self.env.su and not self.env.user.has_group(
            "account_credit.group_credit_manager"
        ):
            raise AccessError(
                self.env._("Only a credit manager can send a partner to legal process.")
            )
        self._get_credit_profile().action_toggle_legal()

    def action_reset_credit_trusted_amount(self) -> None:
        self.write({"credit_trusted_amount": 0.0})

    def action_open_credit_profile(self) -> dict:
        self.check_singleton()
        profile = self._get_credit_profile()
        return {
            "type": "ir.actions.act_window",
            "res_model": "credit.profile",
            "res_id": profile.id,
            "view_mode": "form",
        }

    def action_view_credit_authorizations(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Credit Facilities"),
            "res_model": "credit.facility",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.commercial_partner_id.id)],
            "context": {"active_test": False},
        }

    def _get_credit_document_issues(self):
        self.check_singleton()
        profile = self.sudo().credit_profile_id
        return profile._get_document_issues() if profile else []

    def _get_live_overdue_amount(self):
        self.check_singleton()
        profile = self.sudo().credit_profile_id
        if not profile:
            return 0.0
        profile.invalidate_recordset(["exposure_overdue"])
        return profile.exposure_overdue

    def _check_credit_legal_hold(self) -> None:
        self.check_singleton()
        profile = self.sudo().credit_profile_id
        if profile and profile.hold_active:
            profile.with_env(self.env)._check_credit("invoice", immediate=True)

    def _check_credit_status(
        self, immediate, kind="order", amount=0.0, term_days=None
    ) -> bool:
        self.check_singleton()
        profile = self.commercial_partner_id._get_credit_profile(create=False)
        profile._check_credit(
            kind, amount=amount, immediate=immediate, term_days=term_days
        )
        return True

    def _is_credit_approval_required(
        self, immediate, kind="order", amount=0.0, term_days=None
    ) -> bool:
        self.check_singleton()
        profile = self.commercial_partner_id._get_credit_profile(create=False)
        return bool(
            profile._evaluate(
                kind, amount=amount, immediate=immediate, term_days=term_days
            ).is_approval_required
        )

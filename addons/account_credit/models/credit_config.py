from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

CREDIT_FOLDER_GRANT_CAUSE = "credit.config"
CREDIT_FOLDER_DOMAIN = (
    "[('type', '=', 'folder'),"
    " ('folder_id', '=', False),"
    " ('shortcut_document_id', '=', False)]"
)


class CreditConfig(models.Model):
    _name = "credit.config"
    _inherit = ["mixin.company.config"]
    _description = "Credit and risk configuration per company"

    credit_folder_id = fields.Many2one(
        comodel_name="document.document",
        domain=CREDIT_FOLDER_DOMAIN,
        ondelete="restrict",
        check_company=True,
        help="Root folder of credit-related documentation. Users in the credit "
        "groups gain read or read/write access to the tree under this folder.",
    )
    watch_days = fields.Integer(
        default=30,
        help="A profile whose oldest open receivable is past due by this many "
        "days is put under watch.",
    )
    default_days = fields.Integer(
        default=90,
        help="A profile whose oldest open receivable is past due by this many "
        "days is in default (Basel CRE36.69 uses 90).",
    )
    default_materiality_amount = fields.Float(
        help="Overdue below this amount does not put a profile in default.",
    )
    metrics_window_months = fields.Integer(
        default=12,
        help="Months of paid invoices the payment-behaviour metrics read.",
    )
    exception_max_days = fields.Integer(
        default=90,
        help="Longest a credit exception may run. An exception always carries an "
        "end date; when it ends the profile falls back to its grade and the "
        "policy.",
    )
    entry_grade_id = fields.Many2one(
        comodel_name="credit.grade",
        default=lambda self: self.env.ref(
            "account_credit.credit_grade_cash", raise_if_not_found=False
        ),
        help="Grade every new profile starts in.",
    )
    default_grade_id = fields.Many2one(
        comodel_name="credit.grade",
        default=lambda self: self.env.ref(
            "account_credit.credit_grade_default", raise_if_not_found=False
        ),
        help="Grade a profile is capped at while in default.",
    )
    auto_downgrade = fields.Boolean(
        default=True,
        help="Lower a profile's grade automatically when the scorecard proposes "
        "a worse one. Raising a grade always takes an approved review.",
    )
    review_user_id = fields.Many2one(
        comodel_name="res.users",
        help="Who is assigned the reviews the system schedules.",
    )

    provision_journal_id = fields.Many2one(
        comodel_name="account.journal",
        domain="[('type', '=', 'general')]",
        check_company=True,
        help="Journal the expected credit loss entries are booked in.",
    )
    provision_expense_account_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('account_type', '=', 'expense'), ('deprecated', '=', False)]",
        check_company=True,
        help="Bad-debt expense account.",
    )
    provision_allowance_account_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('account_type', 'in', ('asset_current', 'asset_receivable')), ('deprecated', '=', False)]",
        check_company=True,
        help="Allowance for doubtful accounts, the contra-asset the provision "
        "accumulates in.",
    )
    provision_matrix_id = fields.Many2one(
        comodel_name="credit.provision.matrix",
        check_company=True,
        help="Matrix the expected credit loss runs read. Empty falls back to the "
        "global matrix.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        if any(vals.get("credit_folder_id") for vals in vals_list):
            self._sync_credit_folder_grants()
        return configs

    def write(self, vals):
        result = super().write(vals)
        if "credit_folder_id" in vals:
            self._sync_credit_folder_grants()
        return result

    @api.model
    def _sync_credit_folder_grants(self) -> None:
        # the credit groups reach each company's credit folder, live down its
        # tree, for who holds them in that company: viewers view, users (and
        # administrators, who imply them) edit. One cause for every company,
        # since companies share a folder
        self.flush_model(["credit_folder_id", "company_id"])
        self.env.cr.execute(
            "SELECT DISTINCT credit_folder_id, company_id FROM credit_config"
            " WHERE credit_folder_id IS NOT NULL"
        )
        folders = sorted(self.env.cr.fetchall())
        readonly = self.env.ref("account_credit.group_credit_readonly").id
        user = self.env.ref("account_credit.group_credit_user").id
        wanted = [
            grant
            for folder_id, company_id in folders
            for grant in (
                (folder_id, "group_id", readonly, "view", company_id),
                (folder_id, "group_id", user, "edit", company_id),
            )
        ]
        _debug.lifecycle("credit_folder_grants_synced", folders=folders)
        self.env["document.access"]._sync_caused_grants(
            CREDIT_FOLDER_GRANT_CAUSE, wanted
        )

    @api.constrains("credit_folder_id", "company_id")
    def _check_credit_folder_company(self) -> None:
        wrong = self.filtered(
            lambda c: c.credit_folder_id.company_id.id not in {False, c.company_id.id}
        )
        if wrong:
            raise ValidationError(
                self.env._(
                    "Credit folder cannot be linked to another company.\n- %s",
                    "\n- ".join(
                        f"{c.company_id.name}: {c.credit_folder_id.name}" for c in wrong
                    ),
                )
            )

    @api.constrains("watch_days", "default_days", "exception_max_days")
    def _check_days(self) -> None:
        for config in self:
            if config.watch_days < 0 or config.default_days <= config.watch_days:
                raise ValidationError(
                    self.env._(
                        "Default days must be greater than watch days, both positive."
                    )
                )
            if config.exception_max_days <= 0:
                raise ValidationError(
                    self.env._("An exception must be allowed to last at least a day.")
                )

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.tools import SQL

_debug = DebugLog(__name__)


class WizardAccountAccountMerge(models.TransientModel):
    _name = "wizard.account.account.merge"
    _inherit = ["mixin.account.merge"]
    _description = "Account merge wizard"

    _merge_model = "account.account"
    _merge_records_field = "account_ids"

    account_ids = fields.Many2many(comodel_name="account.account")
    is_group_by_name = fields.Boolean(
        string="Group by name?",
        default=False,
        help="Tick this checkbox if you want accounts to be grouped by name for merging.",
    )
    wizard_line_ids = fields.One2many(
        comodel_name="wizard.account.account.merge.line",
        inverse_name="wizard_id",
        compute="_compute_wizard_line_ids",
        store=True,
        readonly=False,
    )

    def _get_merge_messages(self):
        return {
            "wrong_model": self.env._("This can only be used on accounts."),
            "too_few": self.env._("You must select at least 2 accounts."),
            "merged": self.env._("Accounts successfully merged!"),
        }

    def _get_grouping_key(self, account):
        self.check_singleton()
        grouping_fields = [
            "account_type",
            "non_trade",
            "currency_id",
            "reconcile",
            "active",
        ]
        if self.is_group_by_name:
            grouping_fields.append("name")
        return tuple(account[field] for field in grouping_fields)

    def _get_mergeable_records(self):
        return (
            super()
            ._get_mergeable_records()
            .filtered(lambda a: a.account_type not in ("asset_bank", "asset_cash"))
        )

    @api.depends("is_group_by_name", "account_ids")
    def _compute_wizard_line_ids(self) -> None:
        super()._compute_wizard_line_ids()

    @api.model
    def _prepare_merge(self, accounts):
        code_store_by_id = dict(
            self.env.execute_query(
                SQL(
                    "SELECT id, code_store FROM account_account WHERE id IN %(account_ids)s",
                    account_ids=tuple(accounts.ids),
                    to_flush=accounts._fields["code_store"],
                )
            )
        )
        code_by_company = {}
        for account_id in reversed(accounts.ids):
            code_by_company.update(code_store_by_id[account_id] or {})
        _debug.logic(
            "merged_account_codes_resolved",
            destination=accounts[:1],
            codes=code_by_company,
        )
        return code_by_company

    @api.model
    def _finalize_merge(self, account, companies, code_by_company) -> None:
        self.env.cr.execute(
            SQL(
                """
            UPDATE account_account
               SET code_store = %(code_by_company_json)s
             WHERE id = %(account_to_merge_into_id)s
            """,
                code_by_company_json=json_dumps(code_by_company),
                account_to_merge_into_id=account.id,
            )
        )
        _debug.perf.count("merged_account_codes_written", rows=self.env.cr.rowcount)
        super()._finalize_merge(account, companies, code_by_company)
        self.env.add_to_compute(self.env["account.account"]._fields["tag_ids"], account)

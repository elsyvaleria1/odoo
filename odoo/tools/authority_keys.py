import typing
from collections.abc import Mapping

from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

_AUTHORITY_KEYS: dict[str, str] = {}


def declare_authority_keys(owner: str, *keys: str) -> None:
    for key in keys:
        if (known := _AUTHORITY_KEYS.get(key, owner)) != owner:
            raise ValueError(
                f"authority key {key!r} is declared by {known!r}, not {owner!r}"
            )
    _AUTHORITY_KEYS.update(dict.fromkeys(keys, owner))


def authority_keys() -> Mapping[str, str]:
    return dict(_AUTHORITY_KEYS)


def is_authority_key(key: typing.Any) -> bool:
    return key in _AUTHORITY_KEYS


def strip_authority_keys(context: typing.Any, door: str = "") -> typing.Any:
    if not isinstance(context, Mapping):
        return context
    dropped = [key for key in context if key in _AUTHORITY_KEYS]
    if not dropped:
        return context
    _debug.logic("context.authority_keys_stripped", door=door, keys=sorted(dropped))
    return {key: value for key, value in context.items() if key not in _AUTHORITY_KEYS}


declare_authority_keys(
    "base",
    "uid",
    "api_scope_id",
    "cron_id",
    "install_mode",
    "install_module",
    "install_filename",
    "install_xmlid",
    "_force_unlink",
    "bypass_locked_check",
    "force_deactivate",
    "privilege_reason",
    "access_acting_partner_id",
)

declare_authority_keys("account", "hash_version")
declare_authority_keys("calendar_google", "google_calendar_syncing")
declare_authority_keys("calendar_sync", "calendar_sync_applying")
declare_authority_keys("calendar_microsoft", "microsoft_calendar_syncing")

declare_authority_keys(
    "account",
    "account_unmerge_confirm",
    "chart_template_load",
    "defer_account_code_checks",
    "dynamic_unlink",
    "ignore_missing_tags",
)
declare_authority_keys("account_depreciation", "board_lifecycle", "resume_after_pause")
declare_authority_keys("account_online_synchronization", "delete_sync")
declare_authority_keys("analytic", "account_report_analytic_groupby")
declare_authority_keys("approval", "approver_ids_computation")
declare_authority_keys("auth_oauth", "no_user_creation")
declare_authority_keys("base", "ir_ui_view_loading_records", "onchange_self")
declare_authority_keys("currency_rate_live", "suppress_errors")
declare_authority_keys("hr_expense_stripe", "from_split_wizard")
declare_authority_keys("iap", "disable_iap_update")
declare_authority_keys("l10n_be_hr_payroll", "dmfa_skip_signature", "from_history")
declare_authority_keys("l10n_cl_edi", "cron_skip_connection_errs")
declare_authority_keys("l10n_es_edi_facturae", "forced_invoice")
declare_authority_keys("l10n_it_reports", "l10n_it_reports_monthly_tax_report_options")
declare_authority_keys("loyalty", "loyalty_skip_reward_check")
declare_authority_keys("account_vat", "no_vat_validation")
declare_authority_keys("mrp", "force_date")
declare_authority_keys("quality_mrp", "from_wizard")
declare_authority_keys("resource_asset_account", "ignore_linked_bill_constraint")
declare_authority_keys("resource_asset_product", "asset_part_ledger_write")
declare_authority_keys("sale_renting_planning", "rental_order_updated")
declare_authority_keys(
    "stock",
    "bypass_entire_pack",
    "from_inverse_qty",
    "skip_activity",
    "skip_uom_conversion",
    "stock_unlink_subtree",
)

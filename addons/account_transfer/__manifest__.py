{
    "name": "Automatic Account Transfers",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Accounting",
    "summary": "Allocate account balances through scheduled transfer rules",
    "description": "Configure transfer models with source accounts, destinations, percentages and dates. Generate and inspect the resulting accounting moves.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account",
    ],
    "data": [
        "data/cron.xml",
        "security/ir.access.csv",
        "views/transfer_model_views.xml",
        "views/account_transfer_menus.xml",
    ],
}

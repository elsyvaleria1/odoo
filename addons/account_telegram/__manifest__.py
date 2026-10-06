{
    "name": "Telegram Account Statements",
    "version": "19.0.3.3.0",
    "oldest_upgradable_version": "19.0.3.2.0",
    "category": "Accounting/Accounting",
    "summary": "Generate and deliver partner account statements through Telegram",
    "description": "Adds account-statement commands with period selection, PDF delivery and request logs. Self-service uses the linked partner; querying other customers requires a linked internal user who reads the partner ledger in Odoo (accounting read access); a linked customer gets their own statement only. Requires a configured bot and accounting report access; there is no separate manager-role field on the chat.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "telegram",
        "account",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "data/telegram_command_data.xml",
        "views/telegram_financial_report_log_views.xml",
        "views/account_telegram_menus.xml",
    ],
}

{
    "name": "Electronic Wallet Records",
    "version": "19.0.1.0.4",
    "oldest_upgradable_version": "19.0.1.0.4",
    "category": "Accounting/Accounting",
    "sequence": 90,
    "summary": "Track issuer wallet accounts, cards, balance snapshots and transactions",
    "description": "Stores prepaid-wallet accounts linked to accounting accounts, cards and holders, balance observations, transactions and statements. Provides low-balance indicators and scheduled consolidation of older snapshots. Data must be entered or imported by a separate integration; this addon does not itself post top-ups or consumption as accounting entries.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "account",
        "mail",
        "uom",
    ],
    "data": [
        "security/wallet_security.xml",
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "views/wallet_account_views.xml",
        "views/wallet_card_views.xml",
        "views/wallet_balance_views.xml",
        "views/wallet_transaction_views.xml",
        "views/wallet_statement_views.xml",
        "views/ir_ui_menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "wallet/static/src/home_tile/**/*",
        ],
        "web.assets_unit_tests": [
            "wallet/static/tests/**/*",
        ],
    },
    "application": True,
}

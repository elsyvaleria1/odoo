{
    "name": "Online Bank Synchronization",
    "version": "19.0.2.0.2",
    "oldest_upgradable_version": "19.0.2.0.2",
    "category": "Accounting/Accounting",
    "summary": "Fetch transactions from supported online bank connections",
    "description": "Links bank journals to accounts available through the online synchronization service. Provides transaction fetching, consent renewal and duplicate-review tools. Requires a supported institution, an authorized connection and continued service access.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "credential",
    ],
    "data": [
        "data/config_parameter.xml",
        "data/ir_cron.xml",
        "data/mail_subtype_data.xml",
        "data/mail_template.xml",
        "security/ir.access.csv",
        "views/account_online_sync_views.xml",
        "views/account_bank_statement_view.xml",
        "views/account_journal_view.xml",
        "views/account_online_sync_portal_templates.xml",
        "views/account_journal_dashboard_view.xml",
        "wizards/wizard_account_online_link_connect_account_views.xml",
        "wizards/wizard_account_journal_preview_missing_transaction_views.xml",
        "wizards/wizard_account_bank_statement_line_delete_duplicate_views.xml",
        "wizards/account_online_transaction_preview_views.xml",
        "views/account_online_synchronization_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_online_synchronization/static/src/components/**/*",
            "account_online_synchronization/static/src/hooks/**/*",
            "account_online_synchronization/static/src/js/odoo_fin_connector.js",
        ],
        "web.assets_web_dark": [],
        "web.assets_frontend": [
            "account_online_synchronization/static/src/interactions/*",
        ],
        "web.assets_unit_tests": [
            "account_online_synchronization/static/tests/**/*",
        ],
    },
    "auto_install": [
        "account",
    ],
}

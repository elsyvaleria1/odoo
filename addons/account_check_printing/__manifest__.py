{
    "name": "Check Printing Infrastructure",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Accounting/Accounting",
    "summary": "Configure check numbering and prepare payment checks using installed layouts",
    "description": "Adds bank-journal check sequences, payment check numbers, printing actions and layout settings. Printing requires a compatible check-layout addon, selected journal or company layout and suitable stationery; this addon supplies no country-specific check template.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.access.csv",
        "data/account_check_printing_data.xml",
        "views/account_journal_views.xml",
        "views/account_payment_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_account_payment_print_check_prenumbered_views.xml",
    ],
    "post_init_hook": "create_check_sequence_on_bank_journals",
}

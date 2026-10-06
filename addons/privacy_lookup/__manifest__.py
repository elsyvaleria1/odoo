{
    "name": "Personal Data Lookup",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Hidden",
    "summary": "Find and anonymize personal data linked to a selected identity",
    "description": "Provide a lookup wizard for personal records and actions for supported anonymization operations. Record the executed operations in privacy logs.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mail",
    ],
    "data": [
        "wizards/privacy_lookup_wizard_views.xml",
        "views/privacy_log_views.xml",
        "security/ir.access.csv",
        "data/ir_actions_server_data.xml",
        "views/privacy_lookup_menus.xml",
    ],
    "auto_install": True,
}

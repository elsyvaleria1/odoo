{
    "name": "KPI Digests",
    "version": "1.3",
    "oldest_upgradable_version": "1.2",
    "category": "Marketing",
    "summary": "Email scheduled business-metric digests to subscribers",
    "description": "Configure digest recipients, recurrence and enabled metrics. Provides subscription controls and scheduled delivery of the selected KPI values.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "portal",
    ],
    "data": [
        "security/ir.access.csv",
        "data/digest_data.xml",
        "data/digest_tips_data.xml",
        "data/ir_cron_data.xml",
        "data/res_config_settings_data.xml",
        "views/digest_views.xml",
        "views/digest_templates.xml",
        "views/res_config_settings_views.xml",
        "views/digest_menus.xml",
    ],
}

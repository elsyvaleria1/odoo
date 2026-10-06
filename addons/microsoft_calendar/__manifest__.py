{
    "name": "Outlook Calendar Synchronization",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Productivity",
    "summary": "Synchronize calendar events with authorized Microsoft accounts",
    "description": "Map application calendar events and recurrences to Outlook Calendar. Requires Microsoft connection settings and user authorization.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "microsoft_account",
        "calendar",
    ],
    "data": [
        "data/microsoft_calendar_data.xml",
        "security/ir.access.csv",
        "wizards/wizard_res_users_reset_microsoft_calendar_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
        "views/microsoft_calendar_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "microsoft_calendar/static/src/views/**/*",
        ],
        "web.assets_unit_tests": [
            "microsoft_calendar/static/tests/**/*",
        ],
    },
    "post_init_hook": "init_initiating_microsoft_uuid",
}

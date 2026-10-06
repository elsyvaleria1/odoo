{
    "name": "Outlook Calendar Synchronization",
    "version": "1.4",
    "oldest_upgradable_version": "1.2",
    "category": "Productivity",
    "summary": "Synchronize calendar events with authorized Microsoft accounts",
    "description": "Map application calendar events and recurrences to Outlook Calendar. Requires Microsoft connection settings and user authorization.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "calendar_sync",
        "integration_microsoft",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_res_users_reset_microsoft_calendar_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
        "views/microsoft_calendar_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "calendar_microsoft/static/src/views/**/*",
        ],
    },
    "post_init_hook": "init_initiating_microsoft_uuid",
}

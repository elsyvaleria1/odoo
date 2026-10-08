{
    "name": "Outlook Calendar Synchronization",
    "version": "1.7",
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
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
    ],
}

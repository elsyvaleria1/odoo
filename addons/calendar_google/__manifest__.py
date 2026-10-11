{
    "name": "Google Calendar Synchronization",
    "version": "19.0.2.6.0",
    "oldest_upgradable_version": "19.0.2.1.1",
    "category": "Productivity",
    "summary": "Synchronize calendar events with authorized Google accounts",
    "description": "Map calendar events and recurring appointments between the application and Google Calendar. Requires a configured Google connection and user authorization.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "calendar_sync",
        "integration_google",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
    ],
}

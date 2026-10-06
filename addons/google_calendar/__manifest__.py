{
    "name": "Google Calendar Synchronization",
    "version": "19.0.2.1.1",
    "oldest_upgradable_version": "19.0.2.1.1",
    "category": "Productivity",
    "summary": "Synchronize calendar events with authorized Google accounts",
    "description": "Map calendar events and recurring appointments between the application and Google Calendar. Requires a configured Google connection and user authorization.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "google_account",
        "calendar",
        "credential",
    ],
    "data": [
        "data/google_calendar_data.xml",
        "security/ir.access.csv",
        "wizards/wizard_res_users_reset_google_calendar_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
        "views/google_calendar_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "google_calendar/static/src/scss/google_calendar.scss",
            "google_calendar/static/src/views/**/*",
        ],
        "web.assets_unit_tests": [
            "google_calendar/static/tests/**/*",
        ],
    },
}

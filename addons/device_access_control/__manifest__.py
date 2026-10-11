{
    "name": "Access Control Devices",
    "version": "19.0.4.8.0",
    "oldest_upgradable_version": "19.0.4.7.0",
    "category": "Human Resources",
    "summary": "Synchronize access-device users and schedules and receive access events",
    "description": "Supports configured ISAPI access panels through direct connections or an EHOME bridge. Provides device users, cards, biometric enrollment commands, work schedules and event reception; device connectivity and credentials are required.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "integration",
        "credential",
        "hr",
        "device",
    ],
    "external_dependencies": {
        "python": [
            "defusedxml",
        ],
    },
    "data": [
        "security/access_device_security.xml",
        "security/ir.access.csv",
        "data/access_device_auth_data.xml",
        "data/api_service_data.xml",
        "data/device_profile_access_data.xml",
        "data/device_kind_access_data.xml",
        "data/credential_category_ehome_data.xml",
        "data/credential_category_ehome_field_data.xml",
        "data/ir_cron.xml",
        "views/device_device_views.xml",
        "views/access_device_views.xml",
        "views/access_device_user_views.xml",
        "views/access_event_views.xml",
        "views/access_command_views.xml",
        "views/access_device_dashboard_views.xml",
        "views/access_device_menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "device_access_control/static/src/**/*",
        ],
    },
}

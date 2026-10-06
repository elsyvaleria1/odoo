{
    "name": "Planned Customer Visits",
    "version": "1.1",
    "category": "Human Resources/Planning",
    "summary": "Start and complete planned customer visits and open navigation directions",
    "description": "Adds customer-linked field visits to planning shifts, with start and completion actions and a workflow for declaring visits. Opens navigation using the customer coordinates or address. Location messages require the geolocation feature and location information supplied by the client; the addon does not continuously track employees.",
    "author": "Odoo S.A., AgroMarin",
    "license": "OEEL-1",
    "depends": [
        "planning",
        "sale_planning",
        "web_map",
    ],
    "data": [
        "security/planning_field_service_security.xml",
        "security/ir.access.csv",
        "views/planning_slot_views.xml",
        "views/res_config_settings_views.xml",
        "views/planning_field_service_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "planning_field_service/static/src/**/*",
        ],
        "web.assets_tests": [
            "planning_field_service/static/tests/tours/*",
        ],
    },
    "post_init_hook": "_hide_visits_from_colleagues",
    "uninstall_hook": "_show_published_shifts_again",
}

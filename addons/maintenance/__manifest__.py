{
    "name": "Maintenance",
    "version": "1.11",
    "oldest_upgradable_version": "1.10",
    "category": "Supply Chain/Maintenance",
    "summary": "Track maintenance orders and recurring plans for assets and resources",
    "description": "Provides maintenance orders, plans, team assignment and resource or asset links. Tracks maintenance dates and service-history metrics and supports configured resource blocking. Scheduling and reported metrics depend on entered orders, plans and asset information.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/maintenance",
    "license": "LGPL-3",
    "depends": [
        "approval",
        "mail",
        "resource_asset_product",
        "team",
    ],
    "data": [
        "security/maintenance.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "data/mail_activity_type_data.xml",
        "data/mail_message_subtype_data.xml",
        "data/approval_binding_data.xml",
        "views/maintenance_views.xml",
        "views/maintenance_plan_views.xml",
        "views/resource_asset_views.xml",
        "views/mail_activity_views.xml",
        "wizards/res_config_settings_views.xml",
        "views/maintenance_menus.xml",
    ],
    "demo": [
        "demo/maintenance_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "maintenance/static/src/**/*",
        ],
        "web.assets_tests": [
            "maintenance/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "maintenance/static/tests/*.test.js",
        ],
    },
    "application": True,
}

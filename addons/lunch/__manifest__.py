{
    "name": "Lunch Orders",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Human Resources/Lunch",
    "sequence": 300,
    "summary": "Collect employee meal orders and track lunch account balances",
    "description": "Provides meal suppliers, products, toppings, ordering locations and employee lunch orders. Tracks lunch cash movements and balances and supports configured order and notification schedules. The lunch balance records account for recorded movements; they do not constitute bank transfers.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mail",
    ],
    "data": [
        "security/lunch_security.xml",
        "security/ir.access.csv",
        "reports/lunch_cashmove_report_views.xml",
        "views/lunch_templates.xml",
        "views/lunch_alert_views.xml",
        "views/lunch_cashmove_views.xml",
        "views/lunch_location_views.xml",
        "views/lunch_orders_views.xml",
        "views/lunch_product_views.xml",
        "views/lunch_supplier_views.xml",
        "views/res_config_settings.xml",
        "data/mail_template_data.xml",
        "data/lunch_data.xml",
        "views/lunch_menus.xml",
    ],
    "demo": [
        "demo/lunch_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "lunch/static/src/components/*",
            "lunch/static/src/mixins/*.js",
            "lunch/static/src/views/*",
            "lunch/static/src/scss/lunch_kanban.scss",
        ],
        "web.assets_tests": [
            "lunch/static/tests/tours/*.js",
        ],
        "web.assets_unit_tests": [
            "lunch/static/tests/**/*.test.js",
        ],
    },
    "application": True,
}

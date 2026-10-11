{
    "name": "POS Employee Cashiers",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "summary": "Select eligible employees as POS cashiers using employee credentials",
    "description": "Adds employee cashier selection, PIN and barcode handling, cashier attribution and employee sales reporting. A user still opens the POS session; employee availability follows company and configured access lists, with minimal, basic and advanced employee roles.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "point_of_sale",
        "hr",
    ],
    "data": [
        "views/pos_config.xml",
        "views/pos_order_view.xml",
        "views/pos_payment_view.xml",
        "views/pos_order_report_view.xml",
        "views/single_employee_sales_report.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_pos_session_print_sale_detail_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_hr/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_hr/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_hr/static/tests/unit/**/*",
        ],
    },
    "auto_install": True,
}

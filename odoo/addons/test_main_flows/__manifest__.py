{
    "name": "Application Workflows Tests",
    "version": "1.0",
    "category": "Hidden/Tests",
    "summary": "Test Application Workflows behaviour, including flow",
    "description": "Run regression tests for Application Workflows. Loaded test suites include ``TestUi``, ``TestUiMobile``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web_tour",
        "crm",
        "sale_timesheet",
        "purchase_stock",
        "mrp",
        "account",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_tests": [
            "test_main_flows/static/tests/tours/*.js",
        ],
    },
    "post_init_hook": "_auto_install_enterprise_dependencies",
}

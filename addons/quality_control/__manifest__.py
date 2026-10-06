{
    "name": "Quality Control",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Supply Chain/Quality",
    "sequence": 120,
    "summary": "Generate stock-operation checks and record measurements and quality alerts",
    "description": "Extends quality points with test frequency, sampling and measurement settings. Creates and tracks quality checks on stock operations and provides check-decision wizards and spreadsheet templates. Manufacturing-specific checks require the corresponding integration; recorded results do not independently certify product quality.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/quality",
    "license": "OEEL-1",
    "depends": [
        "quality",
        "spreadsheet_edition",
    ],
    "data": [
        "data/quality_control_data.xml",
        "reports/worksheet_custom_reports.xml",
        "reports/worksheet_custom_report_templates.xml",
        "views/quality_views.xml",
        "views/product_views.xml",
        "views/stock_move_views.xml",
        "views/stock_picking_views.xml",
        "views/product_trace_views.xml",
        "wizards/wizard_quality_check_decide_views.xml",
        "security/ir.access.csv",
        "views/quality_control_menus.xml",
    ],
    "demo": [
        "demo/quality_control_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "quality_control/static/src/**/*",
            (
                "remove",
                "quality_control/static/src/spreadsheet_bundle/**/*",
            ),
        ],
        "spreadsheet.o_spreadsheet": [
            "quality_control/static/src/spreadsheet_bundle/**/*",
        ],
        "web.assets_tests": [
            "quality_control/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "quality_control/static/tests/**/*",
        ],
    },
    "application": True,
}

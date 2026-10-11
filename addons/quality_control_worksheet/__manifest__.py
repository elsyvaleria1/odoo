{
    "name": "Quality Check Worksheets",
    "version": "1.0",
    "category": "Supply Chain/Quality",
    "summary": "Attach configured worksheets to quality checks",
    "description": "Adds worksheet templates and form actions to quality checks and integrates worksheet completion with the check wizard. Requires a worksheet template for the quality-check model; custom fields and layout are supplied through the worksheet framework.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "quality_control",
        "worksheet",
    ],
    "data": [
        "security/ir.access.csv",
        "data/quality_control_data.xml",
        "views/quality_views.xml",
        "views/worksheet_template_views.xml",
        "reports/worksheet_custom_report_templates.xml",
        "views/quality_control_worksheet_menus.xml",
    ],
    "demo": [
        "demo/quality_worksheet_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "quality_control_worksheet/static/src/**/*",
        ],
        "web.assets_tests": [
            "quality_control_worksheet/static/tests/tours/**/*",
        ],
    },
}

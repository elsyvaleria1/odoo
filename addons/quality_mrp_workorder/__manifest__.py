{
    "name": "Work Order Quality Checks",
    "version": "1.0",
    "category": "Supply Chain/Quality",
    "sequence": 50,
    "summary": "Perform quality checks while processing manufacturing work orders",
    "description": "Link quality checks to work orders and provide pass, fail and measurement actions for their check sequence. Adds work-order quality alerts and product quality-control links.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "quality_mrp",
        "mrp_workorder",
        "barcodes",
    ],
    "data": [
        "views/quality_views.xml",
        "views/mrp_workorder_views.xml",
        "reports/worksheet_custom_report_templates.xml",
    ],
    "demo": [
        "demo/mrp_workorder_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "quality_mrp_workorder/static/src/**/*.xml",
            "quality_mrp_workorder/static/src/**/*.js",
        ],
        "web.assets_tests": [
            "quality_mrp_workorder/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}

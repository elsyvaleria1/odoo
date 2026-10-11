{
    "name": "Work-Order Quality Worksheets",
    "version": "1.0",
    "category": "Supply Chain/Quality",
    "summary": "Open quality worksheets from manufacturing work orders",
    "description": "Adds worksheet actions and frontend handling to work-order quality checks using configured worksheet templates.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "quality_control_worksheet",
        "quality_mrp_workorder",
    ],
    "demo": [
        "demo/mrp_workorder_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "quality_mrp_workorder_worksheet/static/src/**/*.js",
        ],
        "web.assets_tests": [
            "quality_mrp_workorder_worksheet/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}

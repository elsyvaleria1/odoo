{
    "name": "Cohort View",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Analyze records by cohort and elapsed periods",
    "description": "Registers the cohort view, its data aggregation and spreadsheet export. Application models must define the date and measure fields for the analysis.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "web",
    ],
    "assets": {
        "web.assets_backend": [
            "web_cohort/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "web_cohort/static/tests/**/*.js",
        ],
    },
    "auto_install": True,
}

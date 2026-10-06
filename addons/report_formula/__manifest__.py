{
    "name": "Formula Reports",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden",
    "summary": "Define report lines and evaluate configured expressions and columns",
    "description": "Provides hierarchical report definitions, expressions, columns, options and report exports. Includes expression evaluation and extension hooks for custom handlers. Business-specific report definitions and data sources are supplied by consuming addons.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
    ],
    "data": [
        "security/ir.access.csv",
        "data/pdf_export_templates.xml",
    ],
    "assets": {
        "report_formula.assets_pdf_export": [
            (
                "include",
                "web._assets_helpers",
            ),
            "web/static/src/scss/pre_variables.scss",
            "web/static/lib/bootstrap/scss/_variables.scss",
            "web/static/lib/bootstrap/scss/_variables-dark.scss",
            "web/static/lib/bootstrap/scss/_maps.scss",
            (
                "include",
                "web._assets_bootstrap_backend",
            ),
            "web/static/fonts/fonts.scss",
            "web/static/src/webclient/actions/reports/report_paged_media.css",
            "report_formula/static/src/scss/pdf_export_template.scss",
        ],
        "web.report_assets_common": [
            "report_formula/static/src/scss/pdf_export_template.scss",
        ],
        "web.assets_backend": [
            "report_formula/static/src/components/**/*",
            "report_formula/static/src/js/**/*",
        ],
        "web.assets_unit_tests": [
            "report_formula/static/tests/**/*",
        ],
    },
    "esm": {
        "bundles": [
            "report_formula.assets_pdf_export",
        ],
    },
}

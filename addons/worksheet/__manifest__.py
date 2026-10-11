{
    "name": "Worksheet Templates",
    "category": "Hidden",
    "summary": "Create worksheet templates backed by configurable models and reports",
    "description": "Provides worksheet template records linked to generated models, actions and report views, with a Studio editing entry point. Consuming business addons connect these templates to their operational records. Template design requires the Studio dependency and appropriate editing permissions.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web_studio",
    ],
    "data": [
        "security/ir.access.csv",
        "views/worksheet_template_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "worksheet/static/src/open_studio_button_widget/*",
        ],
        "web.assets_frontend": [
            "worksheet/static/src/scss/worksheet_portal.scss",
        ],
        "web.report_assets_common": [
            "worksheet/static/src/scss/worksheet_portal.scss",
        ],
        "web_studio.studio_assets_minimal": [
            "worksheet/static/src/client_action/navbar/navbar.js",
        ],
        "web.assets_unit_tests": [
            "worksheet/static/tests/*",
        ],
    },
}

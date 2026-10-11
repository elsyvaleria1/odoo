{
    "name": "Studio Website Forms and Pages",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Create and edit model-linked website forms and pages from Studio",
    "description": "Adds Studio website editor tabs, form creation and lookup endpoints, and generated model page views. Requires the Website builder and Studio dependencies and appropriate editing access; it does not implement an independent website designer.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web_studio",
        "website",
    ],
    "data": [
        "views/templates.xml",
        "views/views.xml",
    ],
    "assets": {
        "web_studio.studio_assets_minimal": [
            "website_studio/static/src/editor_tabs.js",
        ],
        "web.assets_tests": [
            "website_studio/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "website_studio/static/tests/builder/**/*",
        ],
        "website.website_builder_assets": [
            "website_studio/static/src/plugins/**/*",
        ],
    },
    "auto_install": True,
}

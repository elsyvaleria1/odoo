{
    "name": "Hierarchy Views",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Display hierarchical business records in a dedicated view",
    "description": "Add a hierarchy view type and server-side hierarchy reads. Models configure the parent-child relationship used to expand and display their records.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "assets": {
        "web.assets_backend": [
            "web_hierarchy/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "web_hierarchy/static/tests/**/*",
        ],
    },
}

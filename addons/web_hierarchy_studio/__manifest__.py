{
    "name": "Studio Hierarchy View Editor",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Edit hierarchy view settings in Studio",
    "description": "Adds Studio editor components for the hierarchy view type. Requires the corresponding view implementation and Studio.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web_studio",
        "web_hierarchy",
    ],
    "assets": {
        "web_studio.studio_assets_minimal": [
            "web_hierarchy_studio/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "web_hierarchy_studio/static/tests/**/*",
        ],
    },
    "auto_install": True,
}

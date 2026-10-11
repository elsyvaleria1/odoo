{
    "name": "Studio Grid View Editor",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Edit grid view settings in Studio",
    "description": "Adds Studio editor components for the grid view type. Requires the corresponding view implementation and Studio.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web_studio",
        "web_grid",
    ],
    "assets": {
        "web_studio.studio_assets_minimal": [
            "web_grid_studio/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "web_grid_studio/static/tests/**/*",
        ],
    },
    "auto_install": True,
}

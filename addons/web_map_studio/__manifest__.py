{
    "name": "Studio Map View Editor",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Edit map view settings in Studio",
    "description": "Adds Studio editor components for the map view type. Requires the corresponding view implementation and Studio.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web_studio",
        "web_map",
    ],
    "assets": {
        "web_studio.studio_assets_minimal": [
            "web_map_studio/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "web_map_studio/static/tests/**/*",
        ],
    },
    "auto_install": True,
}

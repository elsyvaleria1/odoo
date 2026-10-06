{
    "name": "Record Map Views",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Display address-linked records on maps with optional route rendering",
    "description": "Adds the map view type, contact coordinate handling and map-service settings. Uses Mapbox when a token is configured and OpenStreetMap services otherwise; routing requires Mapbox configuration. Mapping depends on usable addresses or coordinates and external service access.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "web",
    ],
    "data": [
        "views/res_config_settings.xml",
        "views/res_partner_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web_map/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "web_map/static/tests/**/*",
        ],
    },
    "auto_install": True,
}

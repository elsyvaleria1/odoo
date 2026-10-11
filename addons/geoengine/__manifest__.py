{
    "name": "Geospatial Fields and Map Views",
    "version": "19.0.1.20.0",
    "oldest_upgradable_version": "19.0.1.19.0",
    "category": "Productivity/GeoBI",
    "summary": "Store PostGIS geometries and display Odoo records on configurable maps",
    "description": "Adds geometry field types, spatial domain operators and aggregates, raster and vector layer settings, and an OpenLayers map view with styling and editing controls. Includes trail generation and GeoJSON, Shapefile and GeoPackage import/export wizards. Requires PostGIS and the declared Python geometry libraries; consuming addons define the business records and map layers.",
    "author": "Camptocamp,ACSONE SA/NV,Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/geospatial",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "external_dependencies": {
        "python": [
            "shapely",
            "pyproj",
            "pyshp",
        ],
    },
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "data/ir_config_param_data.xml",
        "views/ir_model_fields_views.xml",
        "views/ir_ui_view_views.xml",
        "views/geoengine_view_settings_views.xml",
        "views/geo_raster_layer_view.xml",
        "views/geo_vector_layer_view.xml",
        "wizards/res_config_settings_views.xml",
        "wizards/geo_trail_wizard_views.xml",
        "wizards/geo_io_wizard_views.xml",
        "views/geoengine_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "geoengine/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "geoengine/static/tests/**/*.js",
        ],
    },
    "esm": {
        "external_libs": {
            "ol": "/geoengine/static/lib/ol/ol.esm.js",
            "chroma-js": "/geoengine/static/lib/chroma-js/chroma.esm.js",
            "geostats": "/geoengine/static/lib/geostats/geostats.js",
            "proj4": "/geoengine/static/lib/proj4/proj4.esm.js",
        },
    },
    "pre_init_hook": "_pre_init_postgis",
}

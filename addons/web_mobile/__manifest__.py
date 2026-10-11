{
    "name": "Mobile Host Web Client Integration",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Connect web-client features to APIs exposed by a compatible mobile host",
    "description": "Adds JavaScript wrappers for native host methods and mobile-specific web-client behavior. Native calls require a host exposing OdooDeviceUtility and the relevant methods; this addon does not contain or install an Android or iOS application.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "data": [
        "views/views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web_mobile/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "web_mobile/static/tests/**/*.test.js",
        ],
    },
    "auto_install": True,
}

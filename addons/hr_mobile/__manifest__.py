{
    "name": "Employee Mobile Actions",
    "version": "1.0",
    "category": "Human Resources/Employees",
    "summary": "Use employee features from the mobile client",
    "description": "Adds mobile-specific employee frontend behavior and assets to the backend client.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr",
        "web_mobile",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_mobile/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "hr_mobile/static/tests/**/*.test.js",
        ],
    },
    "auto_install": True,
}

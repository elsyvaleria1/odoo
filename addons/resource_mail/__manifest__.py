{
    "name": "Resource Avatar Cards",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Show resource details through messaging avatar cards",
    "description": "Extend the resource model with avatar-card data for messaging interfaces. Uses the linked resource information instead of requiring a user record.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "resource",
        "mail",
    ],
    "assets": {
        "web.assets_backend": [
            "resource_mail/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "resource_mail/static/tests/**/*",
        ],
    },
    "auto_install": True,
}

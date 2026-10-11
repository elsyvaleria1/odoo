{
    "name": "Resource Messaging",
    "version": "1.1",
    "category": "Hidden",
    "summary": "Give resources a chatter, custody messages and messaging avatar cards",
    "description": "Make resources and the models extending a kind of them mail threads: an asset tracks its changes and posts each operator or manager hand-over in its chatter. Extend the resource model with avatar-card data for messaging interfaces, using the linked resource information instead of requiring a user record.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
    ],
    "data": [
        "data/mail_message_subtype_data.xml",
        "views/resource_resource_views.xml",
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

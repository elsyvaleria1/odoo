{
    "name": "Mail OAuth2 Infrastructure",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Provide reusable OAuth2 authorization and token handling for mail providers",
    "description": "Defines a mail-provider mixin for authorization URLs, token exchange and refresh, state tokens and XOAUTH2 authentication strings. Concrete provider addons must supply endpoint settings, credential fields and integration hooks; installing this infrastructure alone does not configure a mail account.",
    "author": "Odoo Community",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "credential",
    ],
    "auto_install": True,
}

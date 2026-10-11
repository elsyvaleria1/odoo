{
    "name": "Cloudflare Turnstile",
    "version": "2.0",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden",
    "summary": "Check public forms with Cloudflare Turnstile",
    "description": "A captcha provider: the forms of the captcha module get a Turnstile token from a widget shown only when Cloudflare asks the visitor to interact, which the server verifies through the Turnstile service, refusing tokens obtained for another action. The site key is a setting; the secret key is kept in the vault.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "captcha",
        "credential",
        "integration",
    ],
    "data": [
        "data/integration_service_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "captcha_turnstile/static/src/**/*",
        ],
        "web.assets_backend": [
            "captcha_turnstile/static/src/turnstile.js",
        ],
        "web.assets_unit_tests": [
            "captcha_turnstile/static/tests/**/*",
        ],
    },
}

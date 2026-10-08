{
    "name": "reCAPTCHA",
    "version": "2.0",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden",
    "summary": "Check public forms with Google reCAPTCHA v3",
    "description": "A captcha provider: the forms of the captcha module get an invisible reCAPTCHA v3 token, which the server verifies through the reCAPTCHA service, refusing scores below the configured minimum and tokens obtained for another action. The site key and minimum score are settings; the secret key is kept in the vault.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
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
            "captcha_recaptcha/static/src/**/*",
        ],
        "web.assets_backend": [
            "captcha_recaptcha/static/src/js/recaptcha.js",
            "captcha_recaptcha/static/src/xml/recaptcha.xml",
        ],
    },
}

{
    "name": "Google reCAPTCHA",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden",
    "summary": "Check public form submissions using configured reCAPTCHA v3 credentials",
    "description": "Expose the site key to supported frontend forms and verify submitted tokens with reCAPTCHA. Enable the integration and configure its credentials in settings.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "credential",
        "web",
    ],
    "data": [
        "views/res_config_settings_view.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "google_recaptcha/static/src/scss/recaptcha.scss",
            "google_recaptcha/static/src/js/recaptcha.js",
            "google_recaptcha/static/src/interactions/**/*",
        ],
        "web.assets_backend": [
            "google_recaptcha/static/src/xml/recaptcha.xml",
        ],
    },
}

{
    "name": "Cloudflare Turnstile",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Website/Website",
    "summary": "Verify supported website form submissions with Cloudflare Turnstile",
    "description": "Expose Turnstile configuration to frontend forms and check submitted tokens. Requires configured site and secret keys.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "credential",
        "website",
    ],
    "data": [
        "views/res_config_settings_view.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_cf_turnstile/static/src/interactions/**/*.js",
            "website_cf_turnstile/static/src/interactions/**/*.xml",
        ],
        "web.assets_unit_tests": [
            "website_cf_turnstile/static/tests/**/*",
        ],
        "web.assets_unit_tests_setup": [
            "website_cf_turnstile/static/src/interactions/**/*.js",
            "website_cf_turnstile/static/src/interactions/**/*.xml",
        ],
    },
}

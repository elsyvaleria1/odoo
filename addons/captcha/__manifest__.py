{
    "name": "Captcha",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Prove a human sent a public form, through whichever captcha provider is installed",
    "description": "Checks the captcha of every route and form that asks for one (login, signup, password reset, website forms, subscriptions) through one provider chosen in the settings, so the forms do not know which. A provider module (reCAPTCHA, Turnstile) supplies the browser script and the server verification; without one, nothing is checked.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "captcha/static/src/**/*",
        ],
        "web.assets_backend": [
            "captcha/static/src/captcha.js",
            "captcha/static/src/captcha.xml",
        ],
        "web.assets_unit_tests": [
            "captcha/static/tests/**/*",
        ],
    },
}

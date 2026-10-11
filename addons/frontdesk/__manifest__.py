{
    "name": "Visitor Reception",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources/Frontdesk",
    "summary": "Register visitor check-ins and notify their hosts",
    "description": "Provides reception stations, visitor records, host selection, check-in and check-out, and optional drink requests. Email and SMS notifications require the corresponding configured delivery service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr",
        "sms",
    ],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
        "views/frontdesk_report_views.xml",
        "views/frontdesk_drink_views.xml",
        "views/frontdesk_visitor_views.xml",
        "views/frontdesk_frontdesk_views.xml",
        "views/frontdesk_menus.xml",
        "views/frontdesk_templates.xml",
        "views/frontdesk_qr_expiration.xml",
        "data/mail_template_data.xml",
        "data/sms_template_data.xml",
        "data/frontdesk_data.xml",
        "data/frontdesk_templates.xml",
        "data/frontdesk_tour.xml",
    ],
    "demo": [
        "demo/frontdesk_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "frontdesk/static/src/js/**/*",
        ],
        "frontdesk.assets_frontdesk": [
            "frontdesk/static/src/primary_variables.scss",
            "frontdesk/static/src/bootstrap_overridden.scss",
            (
                "include",
                "web._assets_helpers",
            ),
            (
                "include",
                "web._assets_frontend_helpers",
            ),
            (
                "include",
                "web._assets_primary_variables",
            ),
            "web/static/src/scss/pre_variables.scss",
            "web/static/lib/bootstrap/scss/_functions.scss",
            "web/static/lib/bootstrap/scss/_variables.scss",
            "web/static/lib/bootstrap/scss/_variables-dark.scss",
            "web/static/lib/bootstrap/scss/_maps.scss",
            (
                "include",
                "web._assets_bootstrap_frontend",
            ),
            (
                "include",
                "web._assets_bootstrap_backend",
            ),
            "frontdesk/static/src/**/*",
        ],
        "web.assets_tests": [
            "frontdesk/static/tests/tours/**/*",
        ],
    },
    "esm": {
        "bundles": [
            "frontdesk.assets_frontdesk",
        ],
    },
    "application": True,
}

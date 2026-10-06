{
    "name": "Payment Provider Framework",
    "version": "2.4",
    "oldest_upgradable_version": "2.4",
    "category": "Hidden",
    "summary": "Manage payment providers, transactions and saved payment tokens",
    "description": "Provides provider configuration, payment forms, transaction states and hooks for payment operations. Provider addons implement service-specific requests; capture, refunds and tokenization are available only when supported by the selected provider.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "onboarding",
        "portal",
        "integration",
    ],
    "data": [
        "data/ir_actions_server_data.xml",
        "data/payment_method_data.xml",
        "data/payment_provider_data.xml",
        "data/payment_cron.xml",
        "views/express_checkout_templates.xml",
        "views/payment_form_templates.xml",
        "views/portal_templates.xml",
        "views/payment_provider_views.xml",
        "views/payment_method_views.xml",
        "views/payment_transaction_views.xml",
        "views/payment_token_views.xml",
        "views/res_partner_views.xml",
        "security/ir.access.csv",
        "wizards/wizard_payment_transaction_capture_views.xml",
        "wizards/wizard_payment_transaction_view_link_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment/static/src/**/*",
            (
                "remove",
                "payment/static/src/js/payment_wizard_copy_clipboard_field.js",
            ),
        ],
        "web.assets_backend": [
            "payment/static/src/scss/payment_provider.scss",
            "payment/static/src/js/payment_wizard_copy_clipboard_field.js",
        ],
        "web.assets_unit_tests_setup": [
            "payment/static/src/interactions/payment_button.js",
            "payment/static/src/interactions/payment_form.js",
        ],
        "web.assets_unit_tests": [
            "payment/static/tests/**/*.test.js",
        ],
    },
}

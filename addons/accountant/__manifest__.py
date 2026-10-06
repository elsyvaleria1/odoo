{
    "name": "Accounting Workspace",
    "version": "1.1",
    "category": "Accounting/Accounting",
    "sequence": 30,
    "summary": "Expose accounting workspace features and extend invoice review behavior",
    "description": "Adds accounting menus, views and access-group configuration over the accounting dependencies. Enables the invoice in-payment state, extends review eligibility and maintains tax-return journal dashboard visibility. Installation initializes accounting onboarding and conditionally requests the cash-basis reporting addon for configured country cases.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/accounting",
    "license": "OEEL-1",
    "depends": [
        "account",
        "account_depreciation",
    ],
    "data": [
        "views/accountant_menus.xml",
        "data/accountant_data.xml",
        "security/accounting_security.xml",
        "views/res_config_settings.xml",
        "views/partner_views.xml",
    ],
    "demo": [
        "demo/accountant_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "accountant/static/src/js/tours/accountant.js",
        ],
        "web.assets_tests": [
            "accountant/static/tests/tours/*",
        ],
    },
    "application": True,
    "post_init_hook": "_accounting_post_init",
    "uninstall_hook": "uninstall_hook",
}

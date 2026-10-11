{
    "name": "Stripe Expense Cards - Test Mode",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Human Resources/Expenses",
    "sequence": 75,
    "summary": "Simulate card purchases, funding and shipping in Stripe test mode",
    "description": "Extends the Stripe expense-card integration with test purchase, simulated funding and shipping-status wizards. Supplies test-account setup behavior for demonstrations. Requires the parent integration and its test connection; simulated operations do not represent live card transactions.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/expenses",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_expense_stripe",
    ],
    "data": [
        "views/hr_expense_stripe_card_views.xml",
        "views/res_config_settings.xml",
        "wizards/wizard_account_journal_topup_views.xml",
        "wizards/wizard_hr_expense_stripe_card_simulate_purchase_views.xml",
        "wizards/wizard_hr_expense_stripe_card_simulate_shipping_views.xml",
        "security/ir.access.csv",
    ],
    "post_init_hook": "_post_init_hook_setup_issuing_demo",
}

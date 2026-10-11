{
    "name": "Trade Stock Integration Infrastructure",
    "version": "19.0.1.4.0",
    "oldest_upgradable_version": "19.0.1.4.0",
    "category": "Hidden",
    "summary": "Share transfer quantities, statuses and stock-matching helpers across order types",
    "description": "Adds abstract order and line transfer tracking, delivery-delay and stock-match report helpers, and extensions for order links on stock moves and pickings. Also supplies a user warehouse default. Sales and purchase stock bridges implement their concrete logistics flows.",
    "author": "Odoo Community",
    "website": "https://www.odoo.com",
    "license": "Other OSI approved licence",
    "depends": [
        "trade",
        "stock",
        "incoterm",
    ],
}

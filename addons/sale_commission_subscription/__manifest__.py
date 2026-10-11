{
    "name": "Subscription Commissions",
    "version": "1.0",
    "category": "Sales/Commission",
    "sequence": 105,
    "summary": "Calculate commissions from subscription revenue changes",
    "description": "Adds subscription achievement types and recurring-plan filters, using subscription order-log data in commission reporting.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_commission",
        "sale_subscription",
    ],
    "data": [
        "views/sale_commission_plan_view.xml",
    ],
    "auto_install": True,
}

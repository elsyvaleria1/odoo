{
    "name": "Call Subscription Links",
    "version": "1.0",
    "category": "Sales/Subscriptions",
    "summary": "Open related subscriptions from phone calls",
    "description": "Adds subscription counts and a subscription navigation action to call records.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "voip",
        "sale_subscription",
    ],
    "data": [
        "views/phone_call_views.xml",
    ],
    "auto_install": True,
}

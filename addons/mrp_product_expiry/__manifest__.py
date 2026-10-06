{
    "name": "Manufacturing Expiry Warnings",
    "version": "1.0",
    "category": "Supply Chain/Manufacturing",
    "summary": "Warn before consuming expired lots in manufacturing",
    "description": "Checks component lot expiry before marking production done and presents the expired-lot confirmation wizard when required.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mrp",
        "product_expiry",
    ],
    "data": [
        "wizards/wizard_stock_picking_validate_expired_views.xml",
    ],
    "auto_install": True,
}

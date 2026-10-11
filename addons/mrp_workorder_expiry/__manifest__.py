{
    "name": "Work Order Expiry Context",
    "version": "1.0",
    "category": "Supply Chain/Manufacturing",
    "summary": "Set expiry-dialog context on tablet work order actions",
    "description": "Adds skip_expired context to the tablet work order finish and manufacturing-order navigation buttons, plus styling for expiration alerts. This addon adapts those interface paths; expiration dates and their validation belong to its dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mrp_workorder",
        "product_expiry",
    ],
    "data": [
        "wizards/confirm_expiry_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mrp_workorder_expiry/static/**/*",
        ],
    },
    "auto_install": True,
}

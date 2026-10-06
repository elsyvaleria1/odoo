{
    "name": "Purchase Tenders",
    "version": "19.0.1.0.2",
    "oldest_upgradable_version": "19.0.1.0.2",
    "category": "Supply Chain/Purchase",
    "summary": "Invite vendors and compare and award purchase quotations",
    "description": "Adds concrete purchase tender records, offer links, vendor invitation and comparison actions over the shared tender workflow. Awards can allocate quantities among recorded offers and confirm selected orders. Requires prepared purchase quotations and configured suppliers; no external tender portal is supplied here.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "purchase",
        "trade_tender",
    ],
    "data": [
        "security/ir.access.csv",
        "data/purchase_tender_data.xml",
        "wizards/wizard_purchase_order_invite_vendor_views.xml",
        "wizards/wizard_purchase_order_confirm_open_rival_views.xml",
        "views/purchase_tender_views.xml",
        "views/purchase_tender_menus.xml",
    ],
    "demo": [
        "demo/purchase_tender_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "purchase_tender/static/src/**/*.js",
            "purchase_tender/static/src/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "purchase_tender/static/tests/**/*.test.js",
        ],
    },
    "post_init_hook": "post_init_hook",
}

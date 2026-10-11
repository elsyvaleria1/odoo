{
    "name": "Sales Tenders",
    "version": "19.0.1.0.2",
    "oldest_upgradable_version": "19.0.1.0.2",
    "category": "Sales/Sales",
    "summary": "Invite buyers and compare and award sales quotations",
    "description": "Adds concrete sales tender and line models, quotation links and buyer-invitation actions. Uses the shared tender workflow to compare recorded offers and allocate awarded quantities. Requires sales quotation data; buyers are represented by existing contacts and the module does not provide an external bidding marketplace.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "sale",
        "trade_tender",
    ],
    "data": [
        "security/ir.access.csv",
        "data/sale_tender_data.xml",
        "wizards/wizard_sale_order_invite_buyer_views.xml",
        "wizards/wizard_sale_order_confirm_open_rival_views.xml",
        "views/sale_tender_views.xml",
        "views/sale_tender_menus.xml",
    ],
}

{
    "name": "Purchase Competitor Offers",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Purchase",
    "summary": "Compare purchase prices with recorded rival-buyer offers",
    "description": "Links competitor offers to purchase orders and adds vendor-oriented market price, price-gap and recommended-price fields. Applies configured resale-margin and overbid parameters through the shared competition helpers. Requires maintained competitor offers and product pricing inputs; recommendations are calculations from those records.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "purchase",
        "trade_competition",
    ],
    "data": [
        "security/ir.access.csv",
        "views/competitor_offer_views.xml",
        "views/purchase_order_views.xml",
        "views/product_category_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_purchase_order_mark_lost_views.xml",
        "wizards/wizard_purchase_order_line_view_price_history_views.xml",
        "views/purchase_competition_menus.xml",
    ],
}

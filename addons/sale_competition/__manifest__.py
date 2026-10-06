{
    "name": "Sales Competitor Offers",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Compare quotations with recorded competitor prices and capture lost business",
    "description": "Links competitor offers to sales quotations and exposes market-price, gap, margin-floor and recommended-price calculations. Uses configurable margin and undercut settings and the shared loss and activity helpers. The comparison depends on recorded offers and costs; this addon does not obtain competitor pricing automatically.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "sale_margin",
        "trade_competition",
    ],
    "data": [
        "security/ir.access.csv",
        "views/competitor_offer_views.xml",
        "views/sale_order_views.xml",
        "views/product_category_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_sale_order_mark_lost_views.xml",
        "wizards/wizard_sale_order_line_view_price_history_views.xml",
        "views/sale_competition_menus.xml",
    ],
}

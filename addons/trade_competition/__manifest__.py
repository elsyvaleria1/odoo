{
    "name": "Trade Competitor Offers",
    "version": "19.0.1.1.0",
    "category": "Hidden",
    "summary": "Record competitor offers and calculate comparable prices for trade documents",
    "description": "Stores competitor offers, equivalent products, source information and confidence, with currency, unit and configurable freight or financing adjustments. Supplies shared order comparison and loss-recording helpers. Sales and purchase bridges apply the direction-specific comparison; calculated market prices reflect recorded offers rather than a live market feed.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "incoterm",
        "trade",
    ],
    "data": [
        "security/trade_competition_security.xml",
        "security/ir.access.csv",
        "views/competitor_offer_views.xml",
        "views/res_partner_views.xml",
    ],
}

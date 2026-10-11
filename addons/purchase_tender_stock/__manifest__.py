{
    "name": "Purchase Tender Stock Destinations",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Purchase",
    "summary": "Carry stock destination information into purchase tender offers",
    "description": "Extends purchase tender offer preparation with the stock destination and procurement links supplied by the inventory integration.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "purchase_tender",
        "purchase_stock",
    ],
    "data": [
        "views/purchase_views.xml",
    ],
    "auto_install": True,
}

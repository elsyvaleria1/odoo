{
    "name": "Serialized Asset Inventory",
    "version": "1.1",
    "category": "Hidden",
    "summary": "Create and locate physical assets from serialized stock lots",
    "description": "Links tracked product lots to assets and derives asset locations from inventory. Scrapping the corresponding stock disposes of the asset through its lifecycle action.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "resource_asset_product",
        "stock",
    ],
    "data": [
        "views/product_trace_views.xml",
        "views/resource_asset_views.xml",
        "views/stock_location_views.xml",
    ],
    "auto_install": True,
}

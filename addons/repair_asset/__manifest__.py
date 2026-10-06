{
    "name": "Asset Repairs and Parts",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Record repairs and installed parts against physical assets",
    "description": "Links repair orders to assets and records replaced or installed parts when repairs finish. Stock move lines can identify the asset position being serviced.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "repair",
        "resource_asset_stock",
    ],
    "data": [
        "security/ir.access.csv",
        "views/repair_views.xml",
    ],
    "auto_install": True,
}

{
    "name": "Asset Products and Part History",
    "version": "1.5",
    "oldest_upgradable_version": "1.5",
    "category": "Hidden",
    "summary": "Track product-based assets, cost logs and installed parts",
    "description": "Associates product templates with asset kinds and assets with products. Adds asset logs, kind-specific part positions, installation history and review flags for part replacements.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "resource_asset",
        "product",
    ],
    "data": [
        "security/ir.access.csv",
        "views/product_template_views.xml",
        "views/resource_asset_views.xml",
        "views/resource_asset_log_views.xml",
        "views/resource_asset_part_views.xml",
        "views/resource_asset_product_menus.xml",
    ],
    "auto_install": True,
}

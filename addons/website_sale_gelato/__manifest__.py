{
    "name": "eCommerce - Gelato Bridge",
    "category": "Website/Website",
    "summary": "Check Gelato print images before publication and keep Gelato products in separate carts",
    "description": "Extends eCommerce with Gelato-specific checks. Refuses publication when configured print images are missing and refuses clearing print-image data on a published product. Unpublishes a product when template synchronization increases its image count, copies the template description to the eCommerce description, and blocks cart updates that mix Gelato and other non-service products. Marks the existing Gelato standard and express carriers as published. Requires the Gelato sales integration; this addon does not publish products automatically.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "document",
        "sale_gelato",
        "website_sale",
    ],
    "data": [
        "data/delivery_carrier_data.xml",
    ],
    "auto_install": True,
}

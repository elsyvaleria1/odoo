{
    "name": "Pickup Availability Wishlist",
    "category": "Website/Website",
    "summary": "Save unavailable pickup products to the website wishlist",
    "description": "Adds a wishlist action to the pickup delivery form for products unavailable at the selected pickup location.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale_wishlist",
        "website_sale_collect",
    ],
    "data": [
        "views/delivery_form_templates.xml",
    ],
    "auto_install": True,
}

{
    "name": "Website Barcode Lookup Content",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Use Barcode Lookup information on website products",
    "description": "Extend product data and image updates from Barcode Lookup for website presentation. Requires the configured Barcode Lookup integration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "product_barcodelookup",
        "website_sale",
    ],
    "data": [
        "data/product_data.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "website_product_barcodelookup/static/tests/**/*",
        ],
    },
    "auto_install": True,
}

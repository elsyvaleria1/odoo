{
    "name": "POS Mobile Employee Badges",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Scan employee badges through the mobile POS client",
    "description": "Adds mobile-client barcode handling to the POS employee login integration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_hr",
        "web_mobile",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "barcodes/static/src/components/barcode_scanner.scss",
            "pos_hr_mobile/static/src/**/*",
        ],
    },
    "auto_install": True,
}

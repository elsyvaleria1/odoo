{
    "name": "GS1 Barcode Rules",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Supply Chain/Inventory",
    "summary": "Parse GS1 barcode elements into identifiers, quantities and dates",
    "description": "Adds GS1 rule definitions, separator handling and parsing of variable-length elements. Rules can interpret decimal quantities and dates and associate quantities with units.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "barcodes",
        "uom",
    ],
    "data": [
        "data/barcodes_gs1_rules.xml",
        "views/barcodes_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "barcodes_gs1_nomenclature/static/src/js/barcode_parser.js",
            "barcodes_gs1_nomenclature/static/src/js/barcode_service.js",
        ],
        "web.assets_unit_tests": [
            "barcodes_gs1_nomenclature/static/tests/**/*",
        ],
    },
}

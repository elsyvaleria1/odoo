{
    "name": "Barcode Parsing",
    "version": "2.1",
    "oldest_upgradable_version": "2.1",
    "category": "Supply Chain/Inventory",
    "summary": "Scan barcodes and interpret them using configurable nomenclatures",
    "description": "Define barcode nomenclatures and parsing rules, including aliases and encoded values. Provides barcode scanning events for consuming applications.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "data": [
        "security/ir.access.csv",
        "data/barcodes_data.xml",
        "views/barcodes_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "barcodes/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "barcodes/static/tests/*.test.js",
            "barcodes/static/tests/conformance_vectors.js",
            "barcodes/static/tests/barcode_test_helpers.js",
        ],
    },
}

{
    "name": "Import Export Tests",
    "version": "1.0",
    "category": "Hidden",
    "sequence": 3843,
    "summary": "Test Import Export behaviour, including export impex, export, import csv magic",
    "description": "Run regression tests for Import Export. Loaded test suites include ``test_xids``, ``test_boolean_field``, ``test_integer_field``, ``test_float_field``, ``test_decimal_field``.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "web",
        "base_import",
        "website",
    ],
    "data": [
        "security/ir.access.csv",
    ],
}

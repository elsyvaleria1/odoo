{
    "name": "Units of Measure",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Sales/Sales",
    "summary": "Convert and round quantities between compatible measurement units",
    "description": "Define measurement units, reference factors and rounding precision. Quantity conversion checks unit compatibility and applies the configured precision.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
    ],
    "data": [
        "data/uom_data.xml",
        "security/uom_security.xml",
        "security/ir.access.csv",
        "views/uom_uom_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "uom/static/src/components/**/*",
        ],
        "web.assets_unit_tests": [
            "uom/static/tests/**/*",
        ],
    },
}

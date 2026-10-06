{
    "name": "Website Rental Stock Availability",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Calculate rental product availability using warehouse stock and booked periods",
    "description": "Adds date-range availability, preparation time and cart warnings for rental stock products. Stock checks use the website warehouse and configured out-of-stock policy; valid rental dates are required for period-based quantities.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website_sale_renting",
        "website_sale_stock",
        "sale_stock_renting",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_stock_renting/static/src/interactions/**/*",
            "website_sale_stock_renting/static/src/xml/*.xml",
            (
                "after",
                "website_sale_renting/static/src/js/renting_mixin.js",
                "website_sale_stock_renting/static/src/js/renting_mixin.js",
            ),
        ],
        "web.assets_tests": [
            "website_sale_stock_renting/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}

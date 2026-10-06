{
    "name": "Sales Expiration-Aware Forecasts",
    "version": "0.1",
    "category": "Sales/Sales",
    "summary": "Exclude expiring stock from sales availability forecasts",
    "description": "Extend quantity forecasts on sales lines with product expiration rules. Stock due for removal is excluded from the forecast quantities used by the widget.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale_stock",
        "product_expiry",
    ],
    "assets": {
        "web.assets_tests": [
            "sale_stock_product_expiry/static/tests/tours/*.js",
        ],
        "web.assets_backend": [
            "sale_stock_product_expiry/static/src/**/*",
        ],
    },
    "auto_install": True,
}

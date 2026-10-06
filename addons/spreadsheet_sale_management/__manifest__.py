{
    "name": "Quotation Spreadsheets",
    "version": "1.2",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Sales",
    "summary": "Create sales-order spreadsheets from quotation templates",
    "description": "Associate a spreadsheet template with a quotation template and create the order's spreadsheet from it. Provides order navigation, copy handling and cell discussions.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "spreadsheet_edition",
        "sale",
    ],
    "data": [
        "security/ir.access.csv",
        "views/sale_order_template_views.xml",
        "views/sale_order_views.xml",
        "views/sale_order_spreadsheet_views.xml",
        "views/spreadsheet_sale_management_menus.xml",
    ],
    "demo": [
        "demo/sale_order_spreadsheet_demo.xml",
        "demo/sale_order_template_demo.xml",
    ],
    "assets": {
        "spreadsheet.o_spreadsheet": [
            "spreadsheet_sale_management/static/src/bundle/**/*.js",
            "spreadsheet_sale_management/static/src/bundle/**/*.xml",
        ],
        "web.assets_backend": [
            "spreadsheet_sale_management/static/src/assets/**/*.js",
        ],
        "web.assets_unit_tests": [
            "spreadsheet_sale_management/static/tests/**/*",
        ],
    },
    "auto_install": [
        "sale",
    ],
}

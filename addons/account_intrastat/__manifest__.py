{
    "name": "Intrastat Reporting Foundation",
    "version": "1.1",
    "category": "Accounting/Accounting",
    "summary": "Collect trade classifications and invoice data for Intrastat reporting",
    "description": "Provide commodity, transaction and transport reference data and invoice fields for Intrastat. Country modules add their declaration layouts and export formats.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.access.csv",
        "data/code_transaction_data.xml",
        "data/code_transport_data.xml",
        "data/account.intrastat.code.csv",
        "views/account_intrastat_code_view.xml",
        "views/product_view.xml",
        "views/res_config_settings_view.xml",
        "views/account_invoice_view.xml",
        "data/intrastat_goods_report.xml",
        "data/intrastat_services_report.xml",
        "views/report_invoice.xml",
        "views/account_move_view.xml",
        "views/account_return_view.xml",
        "data/intrastat_menus.xml",
    ],
    "demo": [
        "demo/product_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_intrastat/static/src/components/**/*",
            "account_intrastat/static/src/scss/account_intrastat_report.scss",
        ],
    },
}

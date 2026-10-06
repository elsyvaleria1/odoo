{
    "name": "PDF Quotation Builder",
    "category": "Sales/Sales",
    "summary": "Assemble quotation PDFs with product documents and mapped form fields",
    "description": "Attach PDF documents to products and quotations and select how they are included in quotation output. Populate mapped PDF form fields from the sales order.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "document_product",
        "sale",
    ],
    "data": [
        "data/ir_cron.xml",
        "data/sale_pdf_form_field.xml",
        "reports/ir_actions_report.xml",
        "security/ir.access.csv",
        "views/product_document_views.xml",
        "views/quotation_document_views.xml",
        "views/sale_order_template_views.xml",
        "views/sale_order_views.xml",
        "views/sale_pdf_form_field_views.xml",
        "views/sale_pdf_quote_builder_menus.xml",
        "wizards/res_config_settings_views.xml",
    ],
    "demo": [
        "demo/sale_pdf_quote_builder_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_pdf_quote_builder/static/src/js/**/*",
        ],
        "web.assets_tests": [
            "sale_pdf_quote_builder/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}

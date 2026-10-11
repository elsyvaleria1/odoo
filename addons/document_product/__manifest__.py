{
    "name": "Product Document Integration",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Productivity/Documents",
    "summary": "Create a product from selected documents and organize linked product files",
    "description": "Adds product document configuration, counts and navigation. The create-product action creates one product template for the selected documents, links their attachments and uses the first suitable image as its product image; it does not extract a product catalog from file contents.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/documents",
    "license": "Other OSI approved licence",
    "depends": [
        "document",
        "product",
    ],
    "data": [
        "security/ir.access.csv",
        "data/document_folder_data.xml",
        "data/document_tag_data.xml",
        "data/res_company_data.xml",
        "views/res_config_settings_views.xml",
        "views/document_document_views.xml",
        "views/document_document_product_views.xml",
        "views/product_views.xml",
    ],
    "demo": [
        "demo/document_document_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "document_product/static/src/js/**/*",
        ],
        "web.assets_unit_tests": [
            "document_product/static/tests/**/*",
        ],
    },
    "auto_install": True,
}

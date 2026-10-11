{
    "name": "Field Service Product Worksheets",
    "category": "Services/Field Service",
    "summary": "Configure field-service worksheets on sold service products",
    "description": "Adds worksheet template selection to products and propagates the configured worksheet behavior to their field-service project setup.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "industry_fsm_sale",
        "industry_fsm_report",
    ],
    "data": [
        "views/product_template_views.xml",
        "views/project_project_views.xml",
        "views/project_task_views.xml",
        "views/project_portal_project_task_templates.xml",
        "data/product_product_data.xml",
    ],
    "demo": [
        "demo/product_product_demo.xml",
        "demo/ir_model_fields_demo.xml",
        "demo/ir_ui_view_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "industry_fsm_sale_report/static/src/js/tours/industry_fsm_sale_report_tour.js",
        ],
        "web.assets_frontend": [
            "industry_fsm_sale_report/static/src/js/tours/industry_fsm_sale_report_tour.js",
        ],
    },
    "auto_install": True,
    "post_init_hook": "post_init",
}

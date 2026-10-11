{
    "name": "Project Sales Document Demo Data",
    "version": "1.0",
    "category": "Productivity/Documents",
    "summary": "Load sample project sales and document folders when demo data is enabled",
    "description": "Provides demonstration folders, a project template, a service product and a sales order combining Project Documents with project sales. It loads no production data, models or views and does not add product folder-template functionality independently of its dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "document_project",
        "sale_project",
    ],
    "demo": [
        "demo/document_demo.xml",
        "demo/project_sale_demo.xml",
        "demo/res_users_settings_embedded_action_demo.xml",
    ],
    "auto_install": True,
}

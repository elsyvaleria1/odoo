{
    "name": "Project Sales Shift Planning",
    "category": "Sales/Sales",
    "summary": "Link planned sales shifts to projects and sales order lines",
    "description": "Extend planning slots with project and sales-line relationships. Prepare project planning values from sold services and expose them in planning views.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale_planning",
        "sale_project",
        "project_forecast",
    ],
    "data": [
        "views/planning_slot_views.xml",
        "views/planning_templates.xml",
        "views/product_template_views.xml",
    ],
    "auto_install": True,
}

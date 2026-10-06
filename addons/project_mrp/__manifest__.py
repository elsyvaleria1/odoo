{
    "name": "Project Manufacturing Orders",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Link manufacturing orders and bills of materials to projects",
    "description": "Adds project links to production orders and bills of materials, carries them through procurement and exposes production counts and navigation on projects.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mrp",
        "project",
    ],
    "data": [
        "views/mrp_bom_views.xml",
        "views/mrp_production_views.xml",
        "views/project_project_views.xml",
    ],
    "auto_install": True,
}

{
    "name": "Sustainability Initiative Tasks",
    "version": "1.0",
    "category": "ESG",
    "summary": "Track sustainability initiatives as project tasks",
    "description": "Supplies an initiative project, task navigation and an ESG dashboard section for its progress.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "esg",
        "project",
    ],
    "data": [
        "data/project_data.xml",
        "views/project_project_views.xml",
        "views/esg_menus.xml",
    ],
    "demo": [
        "demo/demo_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "esg_project/static/src/**/*",
        ],
    },
    "auto_install": True,
}

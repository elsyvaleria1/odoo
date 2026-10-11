{
    "name": "Website Task Submission",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Website/Website",
    "summary": "Create project tasks from configured website forms",
    "description": "Registers project task fields for website forms and handles submitted contact and description data. Requires a form configured for task creation and an appropriate project; the addon uses the website form builder supplied by its dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website",
        "project",
    ],
    "data": [
        "data/website_project_data.xml",
        "views/project_portal_project_task_template.xml",
        "views/project_portal_project_project_template.xml",
    ],
    "assets": {
        "website.website_builder_assets": [
            "website_project/static/src/js/website_project_editor.js",
        ],
        "project.webclient": [
            "website/static/src/js/utils.js",
            "web/static/src/components/autocomplete/*",
            "website/static/src/components/autocomplete_with_pages/*",
        ],
    },
    "auto_install": True,
}

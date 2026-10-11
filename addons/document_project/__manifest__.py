{
    "name": "Project Document Folders",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Productivity/Documents",
    "summary": "Link document folders to projects and open their contents from project records",
    "description": "Adds project folder configuration, document counts and navigation, and project folder destinations for project and task attachments. Folder creation uses project privacy and company settings, and the addon protects linked project folders from automatic cleanup.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "document",
        "project",
    ],
    "data": [
        "data/document_document_data.xml",
        "data/res_company_data.xml",
        "views/project_views.xml",
        "views/res_config_settings.xml",
    ],
    "demo": [
        "demo/document_project_demo.xml",
    ],
    "auto_install": True,
    "post_init_hook": "_documents_project_post_init",
}

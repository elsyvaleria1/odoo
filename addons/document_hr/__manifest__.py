{
    "name": "Employee Document Folders",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Productivity/Documents",
    "summary": "Manage employee document folders and open them from employee profiles",
    "description": "Adds company HR folder configuration, employee folders and document links on employee records. Folder creation and filing depend on HR document settings; an employee does not receive access to the HR-only employee folder by default.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "document",
        "hr",
    ],
    "data": [
        "data/document_tag_data.xml",
        "views/res_config_settings_views.xml",
        "views/hr_employee_views.xml",
    ],
    "auto_install": True,
    "post_init_hook": "_documents_hr_post_init",
}

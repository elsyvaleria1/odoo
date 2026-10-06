{
    "name": "Mail Plugin Project Tasks",
    "version": "1.0",
    "category": "Services/Project",
    "sequence": 5,
    "summary": "Create project tasks and log email content through the mail plugin",
    "description": "Adds authenticated plugin routes for project search, project creation and task creation from email subject and body, plus project contact data and task logging support. Requires a compatible mail plugin, a bearer token with the declared Outlook scope and access to the target records.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/project",
    "license": "LGPL-3",
    "depends": [
        "project",
        "mail_plugin",
    ],
    "data": [
        "views/project_task_views.xml",
    ],
    "auto_install": True,
}

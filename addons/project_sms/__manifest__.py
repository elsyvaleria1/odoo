{
    "name": "Project Stage SMS Notifications",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Services/Project",
    "summary": "Send text messages when projects or tasks enter configured stages",
    "description": "Adds SMS templates to project phases and task workflow steps. Creation and updates send the configured messages through the SMS service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "project",
        "sms",
    ],
    "data": [
        "views/project_phase_views.xml",
        "views/project_workflow_step_views.xml",
        "views/project_project_views.xml",
        "views/project_task_views.xml",
        "security/ir.access.csv",
    ],
    "auto_install": True,
}

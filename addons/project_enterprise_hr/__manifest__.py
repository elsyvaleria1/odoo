{
    "name": "Project Employee Scheduling Resources",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Resolve task scheduling resources through employee records",
    "description": "Adapts project task resource selection and supplies personal-task email handling for the combined HR and project timeline features.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "project_gantt",
        "hr",
    ],
    "data": [
        "data/todo_mail_alias.xml",
    ],
    "auto_install": True,
}

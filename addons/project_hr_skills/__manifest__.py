{
    "name": "Project Task Skill Filters",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Filter project tasks by their assignees' skills",
    "description": "Expose assignee skills on project tasks and task analysis. Adds task search filters using employee skill records.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "project_hr",
        "hr_skills",
    ],
    "data": [
        "views/project_task_views.xml",
    ],
    "auto_install": True,
}

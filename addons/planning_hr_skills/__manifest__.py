{
    "name": "Planning Skill Filters",
    "version": "1.0",
    "category": "Human Resources/Planning",
    "summary": "Filter planning resources and analysis by recorded employee skills",
    "description": "Exposes current employee skills on planning slots and planning analysis. When a skill filter is present, resource group expansion restricts the displayed resources to matching employees; this does not independently assign shifts or evaluate proficiency.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "planning",
        "hr_skills",
    ],
    "data": [
        "views/planning_slot_views.xml",
    ],
    "auto_install": True,
}

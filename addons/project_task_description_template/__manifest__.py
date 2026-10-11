{
    "name": "Project Task Description Templates",
    "version": "19.0.1.0.0",
    "category": "Services/Project",
    "summary": "Apply reusable description templates to project tasks",
    "description": "Stores description templates with company and project restrictions and adds a selector and apply action to tasks. Checks whether the chosen template is valid for its task. Users maintain the template content and apply it through the supplied task interface.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "project",
    ],
    "data": [
        "security/ir.access.csv",
        "views/project_task_view.xml",
        "views/project_task_description_template_view.xml",
        "views/project_task_description_template_menus.xml",
    ],
}

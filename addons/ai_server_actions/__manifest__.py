{
    "name": "AI Field Update Actions",
    "version": "0.1",
    "category": "Hidden",
    "summary": "Update stored fields with AI-generated values in server actions",
    "description": "Adds an Update with AI evaluation mode and prompt to field-write server actions. Uses the AI field implementation and configured provider to generate the selected stored field value.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "ai_fields",
    ],
    "data": [
        "views/ir_actions_server_views.xml",
    ],
    "auto_install": True,
}

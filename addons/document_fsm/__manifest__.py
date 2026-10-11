{
    "name": "Field Service Document Defaults",
    "version": "1.0",
    "category": "Productivity/Documents",
    "summary": "Keep document integration disabled by default on field-service projects",
    "description": "Adjusts field-service project document setup and document counts when Documents and Field Service are combined.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "document_project",
        "industry_fsm",
    ],
    "auto_install": True,
    "post_init_hook": "_documents_fsm_post_init",
}

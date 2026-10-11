{
    "name": "Approvals",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Approvals",
    "sequence": 190,
    "summary": "Raise, review and configure approval requests from one application",
    "description": "Adds the Approvals application, request categories, manual request forms, templates and document requirements. Checks configured required fields and explicitly assigned attachment requirements at confirmation. Routing and decisions are supplied by the approval engine; categories and approvers determine the workflow.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "approval",
    ],
    "data": [
        "security/ir.access.csv",
        "views/approval_category_views.xml",
        "views/approval_request_views.xml",
        "views/approval_template_views.xml",
        "views/approval_document_requirement_views.xml",
        "views/approval_request_template.xml",
        "data/approval_category_data.xml",
        "views/approvals_menuitem_views.xml",
    ],
    "demo": [
        "demo/00_approval_users_demo.xml",
        "demo/01_approval_groups_demo.xml",
        "demo/approval_demo.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "approval_app/static/tests/tours/**/*",
        ],
    },
    "application": True,
}

{
    "name": "Expense Document Actions",
    "version": "1.0",
    "category": "Productivity/Documents",
    "summary": "Create expenses from eligible documents and open linked expense files",
    "description": "Adds a Documents action for image and PDF files that are not shortcuts or already linked to an expense. The user must be linked to an employee. Also adds expense document counts and navigation; this extension does not promise automatic import of every expense attachment.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "document",
        "hr_expense",
    ],
    "data": [
        "data/ir_actions_server_data.xml",
        "views/hr_expense_views.xml",
    ],
    "demo": [
        "demo/document_document_demo.xml",
    ],
    "auto_install": True,
}

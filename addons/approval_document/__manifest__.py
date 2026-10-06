{
    "name": "Document Access Requests",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Request view or edit access to documents through approval",
    "description": "Adds authenticated access-request pages for eligible document links and a document approval-access adapter. The supplied category routes review to the owner and document managers; approval grants the requested role through document sharing. Shortcut requests must target the underlying document.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "approval",
        "document",
    ],
    "data": [
        "data/approval_category_data.xml",
        "views/document_templates.xml",
    ],
    "auto_install": True,
}

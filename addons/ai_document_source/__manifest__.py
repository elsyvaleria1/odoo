{
    "name": "Document Sources for AI Agents",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Add managed documents to AI agent sources",
    "description": "Links AI source records to Documents, checks source access and supports reindexing and attachment recreation. Requires the configured AI indexing service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "ai",
        "document",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_document_source/static/src/**/*",
        ],
    },
    "auto_install": True,
}

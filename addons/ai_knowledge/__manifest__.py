{
    "name": "AI Knowledge Drafts and Sources",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Draft Knowledge text and use articles as AI agent sources",
    "description": "Adds Knowledge-specific composer configuration and article-backed agent sources with access checks and content extraction. Requires configured AI services.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "ai",
        "knowledge",
    ],
    "data": [
        "data/ai_composer_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_knowledge/static/src/**/*",
        ],
    },
    "auto_install": True,
}

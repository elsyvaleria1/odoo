{
    "name": "AI Accounting Document Context",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Use accounting company context in AI document sorting",
    "description": "Adds the document or environment company to AI sorting context and adapts candidate tools and setup prompts for accounting documents.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "ai_document",
        "document_account",
    ],
    "demo": [
        "demo/ai_document_sort.xml",
        "demo/document_tag.xml",
    ],
    "auto_install": True,
}

{
    "name": "AI Website Page Drafts",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Generate draft website page content with a configured AI agent",
    "description": "Extracts snippet structure and prepares generated HTML for website pages through the configured AI service. Generated page content requires editorial review.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "ai",
        "website",
    ],
    "data": [
        "data/website_ai_agent.xml",
        "views/snippets/snippets.xml",
    ],
    "assets": {
        "website.assets_editor": [
            "ai_website/static/src/components/dialog/add_page_dialog.js",
            "ai_website/static/src/components/dialog/add_page_dialog.xml",
        ],
    },
    "auto_install": True,
}

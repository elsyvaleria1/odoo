{
    "name": "AI Website Chat Snippet",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Place an AI chat entry point in website pages",
    "description": "Adds a website-builder snippet, agent selection and routes to create the corresponding chat channel. Requires a configured AI agent and livechat integration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "ai_website",
        "ai_livechat",
        "html_builder",
    ],
    "data": [
        "views/snippets/snippets.xml",
        "views/snippets/s_ai_livechat.xml",
    ],
    "assets": {
        "im_livechat.assets_embed_core": [
            "ai_website_livechat/static/src/discuss/core/common/**/*",
        ],
        "web.assets_frontend": [
            "ai_website_livechat/static/src/website/components/**/*",
            "ai_website_livechat/static/src/website/interactions/*",
        ],
        "website.assets_inside_builder_iframe": [
            "ai_website_livechat/static/src/website/interactions/edit/**/*",
        ],
        "website.website_builder_assets": [
            "ai_website_livechat/static/src/website/plugins/**/*",
        ],
    },
    "auto_install": True,
}

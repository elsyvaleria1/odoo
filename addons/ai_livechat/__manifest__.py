{
    "name": "AI Livechat Agents",
    "version": "1.1",
    "category": "Productivity/AI",
    "summary": "Assign AI agents to configured livechat rules",
    "description": "Adds agent selection to livechat rules and manages agent participation and response routes. Supports forwarding between scripted chatbots, AI agents and human operators; generation requires an AI provider.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "ai_app",
        "im_livechat",
    ],
    "data": [
        "security/ir_access.xml",
        "data/ai_agent_data.xml",
        "data/ir_job_channel.xml",
        "views/im_livechat_channel_rule_views.xml",
    ],
    "demo": [
        "demo/im_livechat_channel_rule_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_livechat/static/src/discuss/core/common/**/*",
        ],
        "mail.assets_public": [
            "ai_livechat/static/src/discuss/core/common/**/*",
        ],
        "portal.assets_chatter_helpers": [
            "ai_livechat/static/src/discuss/core/common/**/*",
        ],
        "im_livechat.assets_embed_core": [
            "ai_livechat/static/src/discuss/core/common/**/*",
            "ai_livechat/static/src/discuss/embed/common/**/*",
        ],
        "im_livechat.assets_embed_cors": [
            "ai_livechat/static/src/discuss/embed/cors/**/*",
        ],
    },
    "auto_install": True,
}

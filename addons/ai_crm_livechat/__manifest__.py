{
    "name": "AI Livechat Lead Attribution",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Link AI-created leads with their livechat agent",
    "description": "Adapts lead creation for AI livechat context and adds lead counts and navigation on agents.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "ai_crm",
        "ai_livechat",
    ],
    "data": [
        "data/ai_agent.xml",
        "views/ai_agent_views.xml",
    ],
    "auto_install": True,
}

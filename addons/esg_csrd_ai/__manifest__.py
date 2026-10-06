{
    "name": "AI Materiality Suggestions",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden",
    "summary": "Suggest sustainability metrics from company information",
    "description": "Adds a wizard that requests metric suggestions from an AI service and lets users select which suggestions to create. Requires a configured provider and review of generated content.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "ai_app",
        "esg_csrd",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_attachment_data.xml",
        "wizards/wizard_esg_metric_suggest_views.xml",
        "wizards/wizard_esg_metric_create_from_suggestion_views.xml",
        "views/esg_metric_views.xml",
    ],
    "auto_install": True,
}

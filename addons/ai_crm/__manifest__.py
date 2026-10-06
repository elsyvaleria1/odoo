{
    "name": "AI Lead Creation Tools",
    "version": "1.1",
    "category": "Hidden",
    "summary": "Allow configured AI agents to create CRM leads",
    "description": "Registers CRM lead-creation tools and their available parameters for AI agents. The agent configuration controls when the tool is offered.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "ai_app",
        "crm",
    ],
    "data": [
        "data/ir_actions_server_tools.xml",
        "data/ai_topic.xml",
    ],
    "auto_install": True,
}

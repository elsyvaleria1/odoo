{
    "name": "AI Tool Call Approvals",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Hold calls to configured AI tools for approval before applying them",
    "description": "Adds an approval category setting on server-action tools and records proposed calls with arguments, subject, requester and optional assignee. Tools without a category retain their inherited execution flow. Approved calls use the assigned user or requester context; the addon also provides model-operation permissions for tools that explicitly check them.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "ai",
        "approval",
    ],
    "data": [
        "security/ir.access.csv",
        "security/ir_access.xml",
        "data/approval_binding_data.xml",
        "views/ir_actions_server_views.xml",
        "views/ai_tool_call_views.xml",
        "views/ai_tool_model_access_views.xml",
        "views/ai_tool_approval_menus.xml",
    ],
}

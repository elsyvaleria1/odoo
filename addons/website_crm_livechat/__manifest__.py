{
    "name": "Website Lead Live Chat Links",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Link website leads to visitors and open their live chat sessions",
    "description": "Adds visitor information during live-chat lead creation and session counts and navigation on leads. Sessions are reached through the associated visitor; this addon does not provide a separate chat service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_crm",
        "website_livechat",
    ],
    "data": [
        "views/website_crm_lead_views.xml",
    ],
    "auto_install": True,
}

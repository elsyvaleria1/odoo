{
    "name": "AI Invoice Email Drafts",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Enable AI drafting in the invoice email composer",
    "description": "Adds the AI text-draft interface to the invoice-send wizard. Generation uses the configured AI service supplied by the AI integration.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "ai",
        "account",
    ],
    "data": [
        "wizards/wizard_account_move_send_views.xml",
    ],
    "auto_install": True,
}

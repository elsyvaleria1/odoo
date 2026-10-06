{
    "name": "AI Signature Email Drafts",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Enable AI drafting in signature-request emails",
    "description": "Adds the AI text-draft interface to the signature request composer. Requires the configured AI generation service.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sign",
        "ai",
    ],
    "data": [
        "wizards/wizard_sign_request_send_views.xml",
    ],
    "auto_install": True,
}

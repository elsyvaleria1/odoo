{
    "name": "Mail OAuth2",
    "version": "19.0.2.0.0",
    "category": "Hidden",
    "summary": "Authorize mail servers with a vendor's OAuth service",
    "description": "Binds each OAuth mail server to its own connection on a vendor's integration service, which authorizes it through the standard OAuth flow and keeps its tokens fresh; the server logs in to SMTP and IMAP with XOAUTH2. A personal server must be authorized by the account it sends as. Vendor addons supply the service, the scope and the server types; installing this infrastructure alone configures no mail account.",
    "author": "Odoo Community",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
        "integration",
    ],
    "auto_install": True,
}

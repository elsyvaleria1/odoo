{
    "name": "Employee Messaging Bot Settings",
    "version": "1.0",
    "category": "Productivity/Discuss",
    "summary": "Show messaging-bot settings on the employee user form",
    "description": "Adds bot status and notification fields to the user form supplied by the HR integration.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/discuss",
    "license": "Other OSI approved licence",
    "depends": [
        "mail_bot",
        "hr",
    ],
    "data": [
        "views/res_users_views.xml",
    ],
    "auto_install": True,
}

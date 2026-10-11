{
    "name": "Sales SMS Access",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Enable sales users to access the SMS composer",
    "description": "Supplies access-control entries for the SMS composer when Sales and SMS are installed together.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale",
        "sms",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "auto_install": True,
}

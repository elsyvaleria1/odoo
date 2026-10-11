{
    "name": "CRM and Helpdesk Conversion",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Services/Helpdesk",
    "sequence": 19,
    "summary": "Convert helpdesk tickets to leads and create tickets from leads",
    "description": "Adds conversion wizards that transfer inquiry details between CRM leads and helpdesk tickets, with customer and team selection. Requires access to the destination workflow; ticket and lead management remain in the dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "crm",
        "helpdesk",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_crm_lead_convert_ticket_views.xml",
        "wizards/wizard_helpdesk_ticket_convert_lead_views.xml",
        "views/crm_lead_views.xml",
    ],
    "auto_install": True,
}

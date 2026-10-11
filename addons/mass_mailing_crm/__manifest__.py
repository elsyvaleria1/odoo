{
    "name": "Mailing Lead Attribution",
    "version": "1.0",
    "category": "Marketing/Email Marketing",
    "summary": "Count and open CRM leads linked to a mailing source",
    "description": "Adds lead and opportunity counts, analysis navigation and mailing statistics based on matching UTM source IDs. Counts include archived leads; attribution reflects stored source links and does not establish that the mailing caused a conversion.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "crm",
        "mass_mailing",
    ],
    "data": [
        "views/mailing_mailing_views.xml",
    ],
    "demo": [
        "demo/mailing_mailing.xml",
    ],
    "auto_install": True,
}

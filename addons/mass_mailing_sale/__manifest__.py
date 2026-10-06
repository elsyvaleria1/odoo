{
    "name": "Mailing Sales Attribution",
    "version": "1.0",
    "category": "Marketing/Email Marketing",
    "summary": "Report sales orders and accounting amounts linked to a mailing source",
    "description": "Counts source-linked sales orders with lines across order states and sums signed untaxed amounts on source-linked accounting entries outside draft or cancelled states. Adds analysis links and mailing statistics; the amount query is not restricted to customer invoices or a company domain.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale",
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

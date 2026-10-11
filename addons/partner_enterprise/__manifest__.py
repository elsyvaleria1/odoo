{
    "name": "Contact Map View",
    "version": "1.0",
    "category": "Sales/CRM",
    "summary": "Display contacts in a map view from the Contacts application",
    "description": "Declares a partner map view and adds it to the Contacts action. Rendering, geolocation behavior and map-service configuration are supplied by the Map dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "partner",
        "web_map",
    ],
    "data": [
        "views/res_partner_views.xml",
    ],
    "auto_install": True,
}

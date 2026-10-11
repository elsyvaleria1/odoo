{
    "name": "Structured Contact Addresses",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Sales/Sales",
    "sequence": 19,
    "summary": "Split contact streets into components and select configured city records",
    "description": "Adds street-name and number fields with synchronization to the street text, a city catalog and country-specific city selection. City data must be configured or supplied by another addon; this module does not provide a complete global address registry.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "partner",
    ],
    "data": [
        "security/ir.access.csv",
        "views/partner_address_extended.xml",
        "views/res_city_view.xml",
        "views/res_country_view.xml",
        "views/partner_address_extended_menus.xml",
    ],
}

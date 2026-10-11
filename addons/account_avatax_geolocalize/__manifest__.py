{
    "name": "AvaTax Address Coordinates",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Save geolocation information from AvaTax address validation",
    "description": "Extend the partner address validation wizard with geolocation values. Applies the validated address information when the user saves the result.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account_avatax",
        "geocoding",
    ],
    "data": [
        "views/res_partner_views.xml",
    ],
    "auto_install": True,
}

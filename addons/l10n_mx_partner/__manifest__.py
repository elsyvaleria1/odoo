{
    "name": "Mexican Municipalities and Postal Codes",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": "Add Mexico's municipality and SEPOMEX postal code catalogues to contact addresses",
    "description": "Adds the catalogue of Mexican municipalities (INEGI keys per state) and of postal codes with their settlements, an import of the national SEPOMEX file (cpdescarga.txt, downloaded by each database since its licence forbids redistribution) that links every settlement to its municipality, and municipality and postal code fields on contacts. Other modules read a contact's municipality through one SQL expression: the municipality set on it, else the one of its postal code. Municipalities are not preloaded; they come from a module that supplies them, such as l10n_mx_geoengine with its boundaries.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "partner",
    ],
    "countries": [
        "mx",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "views/l10n_mx_municipality_views.xml",
        "views/l10n_mx_postal_code_views.xml",
        "views/res_partner_views.xml",
        "wizards/wizard_l10n_mx_postal_code_import_views.xml",
        "views/partner_l10n_mx_menus.xml",
    ],
}

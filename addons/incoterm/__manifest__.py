{
    "name": "Incoterm Catalog",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Maintain shared delivery-term codes and names for trade documents",
    "description": "Provides the Incoterm reference model, seeded records and maintenance views, including translated names and archive status. Other addons reference this catalog on their documents; this addon does not calculate transport charges or enforce contractual responsibilities.",
    "author": "Odoo S.A., AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "base",
    ],
    "data": [
        "security/ir.access.csv",
        "views/account_incoterms_views.xml",
        "data/account_incoterms_data.xml",
    ],
}

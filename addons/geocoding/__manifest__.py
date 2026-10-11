{
    "name": "Geocoding",
    "version": "3.1",
    "oldest_upgradable_version": "3.1",
    "category": "Hidden",
    "summary": "Convert addresses and coordinates through configured geocoding providers",
    "description": """
Geocoding
=========
Convert addresses into GPS coordinates, and coordinates back into place names,
through a pluggable provider.
    """,
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "credential",
        "web",
    ],
    "data": [
        "security/ir.access.csv",
        "views/geocoder_provider_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "data/data.xml",
    ],
}

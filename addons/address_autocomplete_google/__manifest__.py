{
    "name": "Google Address Autocomplete",
    "version": "2.0",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden/Tools",
    "summary": "Suggest and complete addresses with Google Places",
    "description": "An address autocomplete provider: suggestions and the chosen address's details come from Google Places through its integration service, mapped onto street, number, city, zip, state and country, with Google's attribution under the suggestions. The API key internal users' lookups are made with is kept in the vault.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "address_autocomplete",
        "credential",
        "integration",
    ],
    "data": [
        "data/integration_service_data.xml",
        "views/res_config_settings_views.xml",
    ],
}

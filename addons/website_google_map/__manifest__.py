{
    "name": "Website Contact Google Maps",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Display selected published company contacts on a Google map",
    "description": "Adds a map page and template using published contact addresses and coordinates. The route accepts selected company contact IDs or a domain supplied by an extension and uses the website Google Maps API key; it does not publish unselected contacts automatically.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "geocoding",
        "website_partner",
    ],
    "data": [
        "views/google_map_templates.xml",
    ],
}

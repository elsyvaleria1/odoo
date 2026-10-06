{
    "name": "POS Mobile Customer Displays",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Open a POS customer display through supported mobile application APIs",
    "description": "Loads mobile integration assets into POS and adds presentation-display selection to its navigation bar. Requires a mobile host exposing getDisplays and showDisplayAndGoToUrl for the additional display flow; unsupported hosts retain the inherited customer-display action.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "pos_enterprise",
        "web_mobile",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "web_mobile/static/src/**/*",
            "pos_mobile/static/src/**/*",
        ],
    },
}

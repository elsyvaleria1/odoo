{
    "name": "UrbanPiper Uber Eats Provider",
    "category": "Sales/Point of Sale",
    "summary": "Register Uber Eats as an UrbanPiper delivery provider",
    "description": "Load the Uber Eats provider record for the UrbanPiper POS integration. External order delivery is handled by the configured UrbanPiper connection.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "pos_urban_piper",
    ],
    "data": [
        "data/pos_delivery_provider_data.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_urban_piper_ubereats/static/src/**/*",
        ],
    },
    "auto_install": True,
}

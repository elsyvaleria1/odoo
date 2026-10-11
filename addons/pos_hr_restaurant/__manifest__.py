{
    "name": "Restaurant POS Employee Controls",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Restrict floor-plan editing by cashier role and adjust restaurant idle handling",
    "description": "Hides the restaurant floor-plan editing control from non-admin employees when employee login is enabled. Prevents the restaurant idle timer from resetting on the login screen; these are frontend adaptations to the restaurant and employee POS flows.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_hr",
        "pos_restaurant",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_hr_restaurant/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_hr_restaurant/static/tests/**/*",
        ],
    },
    "auto_install": True,
}

{
    "name": "Website Rental Resource Availability",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Calculate rental service availability from configured planning resources",
    "description": "Extends rental availability for service products with planning enabled and a role whose resources synchronize rental shifts. Counts existing shifts and unavailable work intervals for human resources; products outside these conditions retain the inherited availability flow.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale_renting",
        "sale_renting_planning",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_renting_planning/static/src/interactions/**/*",
        ],
    },
    "auto_install": True,
}

{
    "name": "Sustainability Commuting Settings",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Expose commuting settings with sustainability reporting enabled",
    "description": "Adjusts settings visibility and menu filtering when sustainability reporting and employee fleet-emission features are installed together.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "esg_csrd_hr",
        "esg_hr_fleet",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
}

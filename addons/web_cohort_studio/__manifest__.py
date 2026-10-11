{
    "name": "Studio Cohort View Editor",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Edit cohort view settings in Studio",
    "description": "Adds Studio editor components for the cohort view type. Requires the corresponding view implementation and Studio.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web_studio",
        "web_cohort",
    ],
    "assets": {
        "web_studio.studio_assets_minimal": [
            "web_cohort_studio/static/src/**/*",
        ],
    },
    "auto_install": True,
}

{
    "name": "Molecular Screening",
    "version": "19.0.1.2.0",
    "category": "Productivity",
    "summary": "Track virtual screening campaigns: targets, redocking gate, compounds and docking results",
    "description": "Adds screening campaigns, receptor targets with a redocking validation gate, a compound library keyed on chemical identity with campaign roles, 2D and 3D structures, and docking jobs that stay blocked while their target fails validation. Includes a sketch editor and a 3D viewer; formula, masses, rings, aromaticity, hydrogen-bond counts and Gasteiger partial charges are recomputed on the server, and every property keeps the method that produced it. It records docking runs and results but does not run a docking engine, and it perceives no stereochemistry.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "base",
        "mail",
    ],
    "data": [
        "security/molecular_screening_groups.xml",
        "security/ir.access.csv",
        "wizard/molecular_docking_import_views.xml",
        "wizard/molecular_sketch_views.xml",
        "views/molecular_screening_campaign_views.xml",
        "views/molecular_target_views.xml",
        "views/molecular_compound_views.xml",
        "views/molecular_docking_result_views.xml",
        "views/molecular_screening_menus.xml",
    ],
    "demo": [
        "demo/molecular_validation_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "molecular_screening/static/src/molecule_viewer/*",
            "molecular_screening/static/src/molecule_editor/*",
        ],
    },
    "application": True,
}

{
    "name": "Work Center Physical Assets",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden",
    "summary": "Associate manufacturing work centers with physical assets",
    "description": "Projects work-center machine vocabulary from shared resource identities. Switching machines preserves other representations and operational use, while reservations remain explicit capacity claims.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "resource_mail",
        "mrp",
    ],
    "data": [
        "views/mrp_workcenter_views.xml",
    ],
    "auto_install": True,
}

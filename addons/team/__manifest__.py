{
    "name": "Shared Teams",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Maintain reusable teams, memberships, leaders and application aliases",
    "description": "Defines shared team and membership records with company links, favorites and application-specific usage hooks. Adds user team helpers and alias support for adopting applications. Individual business addons select their team usages and link their documents; installation alone does not enable every listed application workflow.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
    ],
    "data": [
        "security/team_security.xml",
        "security/ir.access.csv",
        "views/team_views.xml",
        "views/team_member_views.xml",
        "views/team_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "team/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "team/static/tests/**/*",
        ],
    },
}

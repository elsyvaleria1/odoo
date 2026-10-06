{
    "name": "Transifex Translation Links",
    "version": "1.0",
    "category": "Hidden/Tools",
    "summary": "Open mapped field and code translations in a Transifex project",
    "description": "Adds translation links and a code-translation interface using project mappings from addon-path .tx/config files. Requires a configured Transifex project URL, a mapped module and a supported language mapping; the remote project must be accessible to the user. Links do not themselves publish translations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
    ],
    "data": [
        "data/transifex_data.xml",
        "views/code_translation_views.xml",
        "security/ir.access.csv",
        "views/transifex_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "transifex/static/src/views/fields/translation_dialog.xml",
            "transifex/static/src/views/*.js",
            "transifex/static/src/views/*.xml",
        ],
    },
}

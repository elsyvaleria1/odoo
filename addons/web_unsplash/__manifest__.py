{
    "name": "Unsplash Image Search",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Hidden",
    "summary": "Search Unsplash from the image picker and save selected images",
    "description": "Adds image-picker search and controller helpers for retrieving Unsplash results and saving selected images as attachments. Uses configured access and application keys and sends download notifications through HTTP requests. Requires Unsplash service access; image suitability and use rights are not established by the search interface.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "credential",
        "html_editor",
    ],
    "data": [
        "views/res_config_settings_view.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "web_unsplash/static/src/frontend/unsplash_beacon.js",
        ],
        "html_editor.assets_media_dialog": [
            "web_unsplash/static/src/media_dialog/**/*",
            "web_unsplash/static/src/unsplash_credentials/**/*",
            "web_unsplash/static/src/unsplash_error/**/*",
            "web_unsplash/static/src/unsplash_service.js",
        ],
        "web.assets_unit_tests": [
            "web_unsplash/static/tests/**/*",
        ],
    },
    "auto_install": True,
}

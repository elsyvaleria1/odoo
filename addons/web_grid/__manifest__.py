{
    "name": "Grid View",
    "version": "0.1",
    "category": "Hidden",
    "summary": "Display and edit grouped measures in a two-dimensional grid",
    "description": "Registers the grid view, cell update handling and availability hooks. Applications supply the row, column and measure fields and the permitted edit behavior.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "assets": {
        "web.assets_backend": [
            "web_grid/static/src/**/*",
        ],
        "web.assets_backend_dark": [],
        "web.assets_unit_tests": [
            "web_grid/static/tests/**/*.test.js",
            "web_grid/static/tests/grid_mock_server.js",
        ],
    },
    "auto_install": True,
}

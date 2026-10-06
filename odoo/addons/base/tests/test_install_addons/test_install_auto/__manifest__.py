{
    "name": "Addon Installation Auto Fixture",
    "version": "1.0",
    "category": "Hidden/Tools",
    "summary": "Exercise automatic addon installation with a scheduled-action fixture",
    "description": "Declare an automatically installed addon depending on the installation base fixture. Loads a scheduled action used by the installation tests.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "test_install_base",
    ],
    "data": [
        "data/ir_cron.xml",
    ],
    "auto_install": True,
}

{
    "name": "Transport Batch Maps and Timelines",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Supply Chain/Inventory",
    "summary": "View transport batches on maps and timelines",
    "description": "Supplies map and Gantt actions and views for inventory transport batches and their vehicle assignments.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_fleet",
        "web_gantt",
        "web_map",
    ],
    "data": [
        "views/batch_gantt.xml",
        "views/stock_picking_view.xml",
        "views/stock_picking_batch.xml",
    ],
    "auto_install": True,
    "uninstall_hook": "uninstall_hook",
}

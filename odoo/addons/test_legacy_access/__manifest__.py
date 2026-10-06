{
    "name": "Stock Access Format Tests",
    "version": "0.0.1",
    "category": "Hidden/Tests",
    "summary": "A module whose access is written as stock Odoo 19.0 writes it",
    "description": "Stands in for a module written for stock Odoo 19.0: its security is ir.model.access lines and ir.rule records, which the loader turns into ir.access rows. ``TestStockAccess`` holds that every user reaches exactly what stock Odoo's check would give.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "base",
    ],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
    ],
}

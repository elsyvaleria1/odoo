{
    "name": "Subcontracting Valuation",
    "version": "0.1",
    "category": "Supply Chain/Manufacturing",
    "summary": "Include subcontracted production in inventory valuation",
    "description": "Extend the finished-product cost update and accounting line valuation for subcontracted manufacturing. Uses the stock valuation and subcontracting workflows.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mrp_subcontracting",
        "mrp_account",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "auto_install": True,
}

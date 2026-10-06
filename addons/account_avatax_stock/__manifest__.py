{
    "name": "AvaTax Shipment Addresses",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Use stock-movement addresses in AvaTax line calculations",
    "description": """
Inventory management for Avatax
=======================================
This module allows for line-level addresses when getting taxes from avatax.

A current limitation is a single order line with more than one stock move (i.e. 10 units of
product A, 2 shipped from warehouse #1 and 8 from warehouse #2). In this case the sale orders should be
split per delivery.
    """,
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_avatax_sale",
        "stock",
    ],
    "auto_install": True,
}

{
    "name": "POS Margin in Sales Analysis",
    "version": "1.1",
    "category": "Sales/Point of Sale",
    "summary": "Include POS line margins in the combined sales analysis report",
    "description": "Extends the POS contribution to Sales Analysis with the sum of POS line margins converted through the report currency rates. POS order processing and sales margin fields are supplied by the dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_sale",
        "sale_margin",
    ],
    "auto_install": True,
}

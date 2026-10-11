{
    "name": "UBL Sales Order Import",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Create sales orders from supported UBL order documents",
    "description": "Map UBL order headers, products and amounts into sales order values. Uses product identification criteria when matching imported order lines.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale",
        "trade_edi_ubl",
    ],
}

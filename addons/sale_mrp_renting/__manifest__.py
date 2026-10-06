{
    "name": "Rental Kit Stock Quantities",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Calculate rental kit deliveries and returns from component stock moves",
    "description": "Adapts rental procurement and delivered quantities for products using kit bills of materials. The kit procurement path requires the rental stock-picking feature. Component move quantities determine moved kit quantities; rental contracts and stock movements are supplied by the dependencies.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale_stock_renting",
        "sale_mrp",
    ],
    "auto_install": True,
}
